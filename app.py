import datetime
import time
import logging
import os
from collections import Counter
from flask import Flask, jsonify, request, render_template
from sqlalchemy import BigInteger, Column, Date, DateTime, DECIMAL, ForeignKey, Integer, String, create_engine, func, text
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker
from apscheduler.schedulers.background import BackgroundScheduler
import pandas as pd
import yfinance as yf
from yfinance import EquityQuery

# Logging Configuration
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# Configurable Parameters
MAX_TICKERS_PER_REQUEST = 50
REQUEST_DELAY_SECONDS = 5
HISTORICAL_START_DATE = "2020-01-01"
YFINANCE_REGION = "th"
DATABASE_URL = "sqlite:///instance/stock_data.db"
FLASK_HOST = "0.0.0.0"
FLASK_PORT = 8080
TOP_N_TICKERS = 100  # Number of top tickers to refresh periodically
LATEST_CACHE_REFRESH_INTERVAL_MINUTES = 1  # Refresh interval for top N tickers
CACHE_TTL_MINUTES = 15  # TTL for on-demand fetched tickers
QUERY_COUNTER_SAVE_INTERVAL_MINUTES = 5  # Save query_counter every 5 minutes
DELTA_SYNC_INTERVAL_DAYS = 1  # Delta sync interval (default daily)

# Global variable to track last cache refresh
last_cache_refresh = None

# Database Models & Setup
Base = declarative_base()

class StockQuote(Base):
    __tablename__ = "stock_quotes"
    ticker = Column(String(10), primary_key=True)
    language = Column(String(10))
    region = Column(String(10))
    quote_type = Column(String(20))
    type_disp = Column(String(20))
    quote_source_name = Column(String(50))
    currency = Column(String(10))
    exchange = Column(String(50))
    full_exchange_name = Column(String(100))
    exchange_timezone_name = Column(String(50))
    exchange_timezone_short_name = Column(String(10))
    gmt_offset_ms = Column(Integer)
    first_trade_date = Column(Date)
    message_board_id = Column(String(50))
    long_name = Column(String(100))
    short_name = Column(String(50))
    display_name = Column(String(50))
    ipo_expected_date = Column(Date)
    previous_name = Column(String(100))
    name_change_date = Column(Date)

class StockPrice(Base):
    __tablename__ = "stock_prices"
    ticker = Column(String(10), ForeignKey("stock_quotes.ticker"), primary_key=True)
    price_date = Column(Date, primary_key=True)
    open_price = Column(DECIMAL(10, 2))
    high_price = Column(DECIMAL(10, 2))
    low_price = Column(DECIMAL(10, 2))
    close_price = Column(DECIMAL(10, 2))
    volume = Column(BigInteger)

class DeltaSyncState(Base):
    __tablename__ = "delta_sync_state"
    id = Column(Integer, primary_key=True)
    last_full_sync = Column(DateTime)
    last_delta_sync = Column(DateTime)

class QueryCount(Base):
    __tablename__ = "query_counts"
    ticker = Column(String(10), primary_key=True)
    count = Column(Integer, default=0)

# Create engine and session
engine = create_engine(DATABASE_URL, echo=False)
Base.metadata.create_all(engine)
Session = sessionmaker(bind=engine)

# Add columns if not exist (for SQLite compatibility)
with engine.connect() as conn:
    try:
        conn.execute(text("ALTER TABLE delta_sync_state ADD COLUMN last_full_sync DATETIME"))
    except:
        pass
    try:
        conn.execute(text("ALTER TABLE delta_sync_state ADD COLUMN last_delta_sync DATETIME"))
    except:
        pass

# In-Memory Latest Price Cache and Query Counter
latest_cache = {}  # Format: {ticker: (price, timestamp)}
query_counter = Counter()  # Tracks query frequency

# Helper Functions
def safe_convert(value, convert_func=lambda x: x):
    if value is None or pd.isna(value):
        return None
    try:
        return convert_func(value)
    except Exception:
        return None

def chunk_list(lst, chunk_size):
    for i in range(0, len(lst), chunk_size):
        yield lst[i:i + chunk_size]

# Data Fetching Functions
def fetch_yf_data(max_tickers_per_request, delay_t, query, start_date=HISTORICAL_START_DATE, end_date=None, sample_size=None):
    all_quotes = []
    offset = 0
    size = sample_size if sample_size is not None else 250
    logger.info("Starting data fetch from yfinance...")
    if sample_size is not None:
        result = yf.screen(query, offset=0, size=sample_size)
        quotes = result.get("quotes", [])
        all_quotes.extend(quotes)
        logger.info(f"Fetched {len(quotes)} quotes (sample size).")
    else:
        while True:
            result = yf.screen(query, offset=offset, size=size)
            quotes = result.get("quotes", [])
            if not quotes:
                break
            all_quotes.extend(quotes)
            logger.info(f"Fetched {len(quotes)} quotes in batch starting at offset {offset}.")
            offset += size
    quotes_df = pd.DataFrame(all_quotes)
    symbols = [quote.get("symbol") for quote in all_quotes if quote.get("symbol")]
    logger.info(f"Total tickers to process: {len(symbols)}")
    historical_data = {}
    processed_since_pause = 0
    for batch_symbols in chunk_list(symbols, max_tickers_per_request):
        tickers_str = " ".join(batch_symbols)
        logger.info(f"Downloading historical data for tickers: {batch_symbols}")
        data = None
        if end_date:
            data = yf.download(tickers=tickers_str, start=start_date, end=end_date, interval="1d", group_by='ticker')
        else:
            data = yf.download(tickers=tickers_str, start=start_date, interval="1d", group_by='ticker')
        if isinstance(data.columns, pd.MultiIndex):
            available_tickers = data.columns.get_level_values(0).unique().tolist()
            for ticker in batch_symbols:
                if ticker in available_tickers:
                    try:
                        ticker_data = data[ticker]
                        historical_data[ticker] = ticker_data
                        logger.debug(f"Historical data fetched for ticker: {ticker}")
                    except Exception as e:
                        logger.error(f"Error processing ticker {ticker}: {e}")
        else:
            ticker = batch_symbols[0]
            historical_data[ticker] = data
            logger.debug(f"Historical data fetched for single ticker: {ticker}")
        processed_since_pause += len(batch_symbols)
        if processed_since_pause >= 1000:
            logger.info(f"Processed {processed_since_pause} tickers since last pause, pausing for 60 seconds.")
            time.sleep(60)
            processed_since_pause = 0
        else:
            time.sleep(delay_t)
    logger.info("Completed fetching historical data.")
    return quotes_df, historical_data

def update_database(quotes_df, historical_data, upsert=False):
    session = Session()
    stock_quote_mappings = []
    for idx, row in quotes_df.iterrows():
        ticker = row.get("symbol")
        if not ticker:
            continue
        mapping = {
            "ticker": ticker,
            "language": row.get("language"),
            "region": row.get("region"),
            "quote_type": row.get("quoteType"),
            "type_disp": row.get("typeDisp"),
            "quote_source_name": row.get("quoteSourceName"),
            "currency": row.get("currency"),
            "exchange": row.get("exchange"),
            "full_exchange_name": row.get("fullExchangeName"),
            "exchange_timezone_name": row.get("exchangeTimezoneName"),
            "exchange_timezone_short_name": row.get("exchangeTimezoneShortName"),
            "gmt_offset_ms": safe_convert(row.get("gmtOffSetMilliseconds"), int),
            "first_trade_date": safe_convert(row.get("firstTradeDateMilliseconds"), lambda x: datetime.datetime.fromtimestamp(x / 1000).date()),
            "message_board_id": row.get("messageBoardId"),
            "long_name": row.get("longName"),
            "short_name": row.get("shortName"),
            "display_name": row.get("displayName"),
            "ipo_expected_date": None,
            "previous_name": row.get("prevName"),
            "name_change_date": None,
        }
        ipo = row.get("ipoExpectedDate")
        if ipo:
            try:
                mapping["ipo_expected_date"] = datetime.datetime.strptime(ipo, "%Y-%m-%d").date()
            except Exception:
                mapping["ipo_expected_date"] = None
        ncd = row.get("nameChangeDate")
        if ncd:
            try:
                mapping["name_change_date"] = datetime.datetime.strptime(ncd, "%Y-%m-%d").date()
            except Exception:
                mapping["name_change_date"] = None
        stock_quote_mappings.append(mapping)
    if upsert:
        for mapping in stock_quote_mappings:
            session.merge(StockQuote(**mapping))
        session.commit()
    else:
        session.bulk_insert_mappings(StockQuote, stock_quote_mappings)
        session.commit()
    stock_price_mappings = []
    for ticker, df in historical_data.items():
        if df is None or df.empty:
            continue
        for date, data_row in df.iterrows():
            price_date = date.date() if isinstance(date, datetime.datetime) else date
            mapping = {
                "ticker": ticker,
                "price_date": price_date,
                "open_price": safe_convert(data_row.get("Open"), float),
                "high_price": safe_convert(data_row.get("High"), float),
                "low_price": safe_convert(data_row.get("Low"), float),
                "close_price": safe_convert(data_row.get("Close"), float),
                "volume": safe_convert(data_row.get("Volume"), int)
            }
            stock_price_mappings.append(mapping)
    if upsert:
        for mapping in stock_price_mappings:
            session.merge(StockPrice(**mapping))
        session.commit()
    else:
        session.bulk_insert_mappings(StockPrice, stock_price_mappings)
        session.commit()
    session.close()

# Global Sync Job Functions
def full_sync():
    logger.info("Starting Full Sync...")
    query_th = EquityQuery("eq", ["region", YFINANCE_REGION])
    quotes_df_th, historical_data_th = fetch_yf_data(
        max_tickers_per_request=MAX_TICKERS_PER_REQUEST,
        delay_t=REQUEST_DELAY_SECONDS,
        query=query_th,
        start_date=HISTORICAL_START_DATE,
    )
    query_us = EquityQuery("is-in", ["exchange", "NMS", "NYQ"])
    quotes_df_us, historical_data_us = fetch_yf_data(
        max_tickers_per_request=MAX_TICKERS_PER_REQUEST,
        delay_t=REQUEST_DELAY_SECONDS,
        query=query_us,
        start_date=HISTORICAL_START_DATE,
    )
    quotes_df = pd.concat([quotes_df_th, quotes_df_us], ignore_index=True)
    historical_data = {**historical_data_th, **historical_data_us}
    update_database(quotes_df, historical_data, upsert=False)
    session = Session()
    state = session.query(DeltaSyncState).filter_by(id=1).first()
    if not state:
        state = DeltaSyncState(id=1)
    state.last_full_sync = datetime.datetime.now()
    session.merge(state)
    session.commit()
    session.close()
    logger.info("Full Sync Completed.")

def delta_sync():
    logger.info("Starting Delta Sync...")
    session = Session()
    state = session.query(DeltaSyncState).filter_by(id=1).first()
    session.close()
    today = datetime.datetime.now().date()
    two_days_ago = today - datetime.timedelta(days=2)
    query_th = EquityQuery("eq", ["region", YFINANCE_REGION])
    quotes_df_th, historical_data_th = fetch_yf_data(
        max_tickers_per_request=MAX_TICKERS_PER_REQUEST,
        delay_t=REQUEST_DELAY_SECONDS,
        query=query_th,
        start_date=two_days_ago.strftime("%Y-%m-%d"),
        end_date=today.strftime("%Y-%m-%d"),
    )
    query_us = EquityQuery("is-in", ["exchange", "NMS", "NYQ"])
    quotes_df_us, historical_data_us = fetch_yf_data(
        max_tickers_per_request=MAX_TICKERS_PER_REQUEST,
        delay_t=REQUEST_DELAY_SECONDS,
        query=query_us,
        start_date=two_days_ago.strftime("%Y-%m-%d"),
        end_date=today.strftime("%Y-%m-%d"),
    )
    quotes_df = pd.concat([quotes_df_th, quotes_df_us], ignore_index=True)
    historical_data = {**historical_data_th, **historical_data_us}
    update_database(quotes_df, historical_data, upsert=True)
    session = Session()
    state = session.query(DeltaSyncState).filter_by(id=1).first()
    if not state:
        state = DeltaSyncState(id=1)
    state.last_delta_sync = datetime.datetime.now()
    session.merge(state)
    session.commit()
    session.close()
    logger.info("Delta Sync Completed.")

# New functions to force sync for a specific ticker
def force_full_sync_ticker(ticker):
    logger.info(f"Starting full sync for ticker: {ticker}")
    try:
        t = yf.Ticker(ticker)
        info = t.info
    except Exception as e:
        logger.error(f"Error fetching ticker info for {ticker}: {e}")
        raise
    mapping = {
        "ticker": ticker,
        "language": None,
        "region": YFINANCE_REGION,
        "quote_type": info.get("quoteType"),
        "type_disp": None,
        "quote_source_name": info.get("quoteSourceName"),
        "currency": info.get("currency"),
        "exchange": info.get("exchange"),
        "full_exchange_name": info.get("fullExchangeName"),
        "exchange_timezone_name": info.get("exchangeTimezoneName"),
        "exchange_timezone_short_name": info.get("exchangeTimezoneShortName"),
        "gmt_offset_ms": info.get("gmtOffSetMilliseconds"),
        "first_trade_date": None,
        "message_board_id": info.get("messageBoardId"),
        "long_name": info.get("longName"),
        "short_name": info.get("shortName"),
        "display_name": info.get("displayName"),
        "ipo_expected_date": None,
        "previous_name": None,
        "name_change_date": None,
    }
    if info.get("firstTradeDate"):
        try:
            mapping["first_trade_date"] = datetime.datetime.fromtimestamp(info["firstTradeDate"]).date()
        except Exception:
            mapping["first_trade_date"] = None
    df = t.history(start=HISTORICAL_START_DATE, interval="1d")
    quotes_df = pd.DataFrame([{"symbol": ticker, **mapping}])
    historical_data = {ticker: df}
    update_database(quotes_df, historical_data, upsert=True)
    logger.info(f"Completed full sync for ticker: {ticker}")

def force_delta_sync_ticker(ticker):
    logger.info(f"Starting delta sync for ticker: {ticker}")
    try:
        t = yf.Ticker(ticker)
        info = t.info
    except Exception as e:
        logger.error(f"Error fetching ticker info for {ticker}: {e}")
        raise
    mapping = {
        "ticker": ticker,
        "language": None,
        "region": YFINANCE_REGION,
        "quote_type": info.get("quoteType"),
        "type_disp": None,
        "quote_source_name": info.get("quoteSourceName"),
        "currency": info.get("currency"),
        "exchange": info.get("exchange"),
        "full_exchange_name": info.get("fullExchangeName"),
        "exchange_timezone_name": info.get("exchangeTimezoneName"),
        "exchange_timezone_short_name": info.get("exchangeTimezoneShortName"),
        "gmt_offset_ms": info.get("gmtOffSetMilliseconds"),
        "first_trade_date": None,
        "message_board_id": info.get("messageBoardId"),
        "long_name": info.get("longName"),
        "short_name": info.get("shortName"),
        "display_name": info.get("displayName"),
        "ipo_expected_date": None,
        "previous_name": None,
        "name_change_date": None,
    }
    if info.get("firstTradeDate"):
        try:
            mapping["first_trade_date"] = datetime.datetime.fromtimestamp(info["firstTradeDate"]).date()
        except Exception:
            mapping["first_trade_date"] = None
    today = datetime.datetime.now().date()
    two_days_ago = today - datetime.timedelta(days=2)
    df = t.history(start=two_days_ago.strftime("%Y-%m-%d"), end=today.strftime("%Y-%m-%d"), interval="1d")
    quotes_df = pd.DataFrame([{"symbol": ticker, **mapping}])
    historical_data = {ticker: df}
    update_database(quotes_df, historical_data, upsert=True)
    logger.info(f"Completed delta sync for ticker: {ticker}")

# Latest Cache Refresh Function for Top N Tickers
def refresh_top_n_tickers():
    global last_cache_refresh
    logger.info("Refreshing latest prices for top N tickers...")
    session = Session()
    # Get top N tickers based on query frequency
    top_tickers = [ticker for ticker, _ in query_counter.most_common(TOP_N_TICKERS)]
    session.close()
    
    for batch_tickers in chunk_list(top_tickers, MAX_TICKERS_PER_REQUEST):
        tickers_str = " ".join(batch_tickers)
        logger.info(f"Fetching latest prices for batch: {batch_tickers}")
        try:
            data = yf.Tickers(tickers_str)
            for ticker in batch_tickers:
                try:
                    last_price = data.tickers[ticker].fast_info["last_price"]
                    latest_cache[ticker] = (last_price, datetime.datetime.now())
                except Exception as e:
                    logger.error(f"Error fetching latest price for {ticker}: {e}")
        except Exception as e:
            logger.error(f"Error fetching batch for tickers {batch_tickers}: {e}")
        time.sleep(REQUEST_DELAY_SECONDS)
    last_cache_refresh = datetime.datetime.now()  # Update last cache refresh time
    logger.info(f"Refreshed latest prices for {len(top_tickers)} top tickers.")

# On-Demand Latest Price Fetching
def get_latest_price(ticker):
    query_counter[ticker] += 1  # Increment query count
    if ticker in latest_cache:
        price, timestamp = latest_cache[ticker]
        if (datetime.datetime.now() - timestamp).total_seconds() / 60 < CACHE_TTL_MINUTES:
            return price  # Return cached price if within TTL
    try:
        data = yf.Ticker(ticker)
        last_price = data.fast_info["last_price"]
        latest_cache[ticker] = (last_price, datetime.datetime.now())
        return last_price
    except Exception as e:
        logger.error(f"Error fetching latest price for {ticker}: {e}")
        return None

# Save Query Counter to Database
def save_query_counter():
    session = Session()
    for ticker, count in query_counter.items():
        existing = session.query(QueryCount).filter_by(ticker=ticker).first()
        if existing:
            existing.count += count
        else:
            session.add(QueryCount(ticker=ticker, count=count))
    session.commit()
    session.close()
    logger.info("Saved query_counter to database.")

# Load Query Counter from Database
def load_query_counter():
    session = Session()
    query_counts = session.query(QueryCount).all()
    for qc in query_counts:
        query_counter[qc.ticker] = qc.count
    session.close()
    logger.info("Loaded query_counter from database.")

# -------------------------------
# Flask App and API Endpoints
app = Flask(__name__)
api_stats = Counter()

# -------------------------------
# New API Endpoints for Dashboard
# -------------------------------

# Unified ticker endpoint: returns meta info and historical data for a selected ticker
@app.route("/api/unified")
def get_unified_ticker():
    ticker = request.args.get("ticker")
    if not ticker:
        return jsonify({"error": "Ticker parameter is required"}), 400
    session = Session()
    quote = session.query(StockQuote).filter_by(ticker=ticker).first()
    prices = session.query(StockPrice).filter_by(ticker=ticker).all()
    session.close()
    if not quote:
        return jsonify({"error": "Ticker not found"}), 404
    unified_data = {
        "ticker": ticker,
        "long_name": quote.long_name,
        "exchange": quote.exchange,
        "latest_price": latest_cache.get(ticker, (None, None))[0],
        "historical_data": [
            {
                "date": price.price_date.strftime("%Y-%m-%d"),
                "open": float(price.open_price) if price.open_price is not None else None,
                "high": float(price.high_price) if price.high_price is not None else None,
                "low": float(price.low_price) if price.low_price is not None else None,
                "close": float(price.close_price) if price.close_price is not None else None,
                "volume": price.volume,
            }
            for price in prices
        ]
    }
    return jsonify(unified_data)

# Data quality endpoint: returns high-level quality metrics of our stored data
@app.route("/api/data_quality")
def data_quality():
    session = Session()
    total_tickers = session.query(StockQuote).count()
    missing_long_name = session.query(StockQuote).filter(StockQuote.long_name.is_(None)).count()
    missing_exchange = session.query(StockQuote).filter(StockQuote.exchange.is_(None)).count()
    quotes = session.query(StockQuote).all()
    total_fields = len(quotes) * 2  # using long_name and exchange as key fields
    filled_fields = sum((1 if q.long_name is not None else 0) + (1 if q.exchange is not None else 0) for q in quotes)
    completeness = (filled_fields / total_fields * 100) if total_fields > 0 else 0
    duplicate_entries = 0
    duplicates = session.query(
        StockPrice.ticker, StockPrice.price_date, func.count(StockPrice.ticker).label("dup_count")
    ).group_by(StockPrice.ticker, StockPrice.price_date).having(func.count(StockPrice.ticker) > 1).all()
    for dup in duplicates:
        duplicate_entries += dup.dup_count - 1
    session.close()
    data_quality_metrics = {
        "total_tickers": total_tickers,
        "completeness": round(completeness, 2),
        "missing_fields": missing_long_name + missing_exchange,
        "duplicates": duplicate_entries
    }
    return jsonify(data_quality_metrics)


@app.route("/api/ticker_traffic")
def ticker_traffic():
    top_tickers = query_counter.most_common(200)
    data = [{"ticker": t, "count": count} for t, count in top_tickers]
    return jsonify(data)

@app.route("/api/cache_info")
def cache_info():
    global last_cache_refresh
    cache_job = scheduler.get_job("cache_refresh")
    if cache_job and cache_job.next_run_time:
        now_aware = datetime.datetime.now(tz=cache_job.next_run_time.tzinfo)
        diff_seconds = (cache_job.next_run_time - now_aware).total_seconds()
        if diff_seconds >= 60:
            next_cache_refresh = f"{int(diff_seconds // 60)} minutes"
        else:
            next_cache_refresh = f"{int(diff_seconds)} seconds"
    else:
        next_cache_refresh = "N/A"
    return jsonify({
        "last_cache_refresh": last_cache_refresh.isoformat() if last_cache_refresh else None,
        "next_cache_refresh": next_cache_refresh
    })

@app.before_request
def before_request():
    if request.path.startswith('/api/'):
        api_stats[request.path] += 1

@app.route("/api/latest")
def get_latest():
    ticker = request.args.get("ticker")
    if not ticker:
        return jsonify({"error": "Ticker parameter is required"}), 400
    price = get_latest_price(ticker)
    if price is not None:
        timestamp = latest_cache.get(ticker, (None, datetime.datetime.now()))[1]
        return jsonify({ticker: price, "timestamp": timestamp.isoformat()})
    else:
        return jsonify({"error": "Unable to fetch latest price"}), 500

@app.route("/api/assets")
def get_assets():
    session = Session()
    quotes = session.query(StockQuote).all()
    session.close()
    assets = []
    for quote in quotes:
        latest = latest_cache.get(quote.ticker, (None, None))
        assets.append({
            "ticker": quote.ticker,
            "long_name": quote.long_name,
            "short_name": quote.short_name,
            "region": quote.region,
            "exchange": quote.exchange,
            "latest_price": latest[0],
            "updated_at": latest[1].isoformat() if latest[1] else None
        })
    return jsonify(assets)

@app.route("/api/historical")
def get_historical():
    ticker = request.args.get("ticker")
    if not ticker:
        return jsonify({"error": "Ticker parameter is required"}), 400
    session = Session()
    prices = session.query(StockPrice).filter_by(ticker=ticker).all()
    session.close()
    if not prices:
        return jsonify({"error": "No historical data found for ticker"}), 404
    data = []
    for price in prices:
        record = {
            "date": price.price_date.strftime("%Y-%m-%d"),
            "open": float(price.open_price) if price.open_price is not None else None,
            "high": float(price.high_price) if price.high_price is not None else None,
            "low": float(price.low_price) if price.low_price is not None else None,
            "close": float(price.close_price) if price.close_price is not None else None,
            "volume": price.volume,
        }
        data.append(record)
    response = {"ticker": ticker, "historical_data": data}
    return jsonify(response)

@app.route("/api/stats")
def get_stats():
    session = Session()
    total_tickers = session.query(StockQuote).count()
    stock_prices_count = session.query(StockPrice).count()
    delta_sync_state_count = session.query(DeltaSyncState).count()
    query_counts_count = session.query(QueryCount).count()
    region_counts = session.query(StockQuote.region, func.count(StockQuote.ticker)).group_by(StockQuote.region).all()
    state = session.query(DeltaSyncState).filter_by(id=1).first()
    session.close()
    
    total = sum(count for _, count in region_counts)
    region_distribution = {region: {"count": count, "percentage": (count / total * 100) if total > 0 else 0}
                           for region, count in region_counts}
    
    last_full_sync = state.last_full_sync.isoformat() if state and state.last_full_sync else None
    last_delta_sync = state.last_delta_sync.isoformat() if state and state.last_delta_sync else None
    
    db_file = 'instance/stock_data.db'
    db_size = os.path.getsize(db_file) / (1024 * 1024)
    db_size_str = f"{db_size:.2f} MB" if db_size < 1024 else f"{db_size / 1024:.2f} GB"
    
    stats = {
        "total_tickers": total_tickers,
        "db_size": db_size_str,
        "cache_hit_rate": "100%",
        "api_requests_24h": sum(api_stats.values()),
        "table_records": {
            "stock_quotes": total_tickers,
            "stock_prices": stock_prices_count,
            "delta_sync_state": delta_sync_state_count,
            "query_counts": query_counts_count
        },
        "region_distribution": region_distribution,
        "last_full_sync": last_full_sync,
        "last_delta_sync": last_delta_sync,
        "cache_size": len(latest_cache),
        "api_stats": dict(api_stats)
    }
    return jsonify(stats)

@app.route("/api/sync/full", methods=["POST"])
def sync_full():
    data = request.get_json() or {}
    ticker = data.get("ticker")
    try:
        if ticker:
            force_full_sync_ticker(ticker)
            return jsonify({"message": f"Full sync for ticker {ticker} completed."})
        else:
            full_sync()
            return jsonify({"message": "Global full sync completed."})
    except Exception as e:
        logger.error(f"Error in full sync: {e}")
        return jsonify({"error": str(e)}), 500

@app.route("/api/sync/delta", methods=["POST"])
def sync_delta():
    data = request.get_json() or {}
    ticker = data.get("ticker")
    try:
        if ticker:
            force_delta_sync_ticker(ticker)
            return jsonify({"message": f"Delta sync for ticker {ticker} completed."})
        else:
            delta_sync()
            return jsonify({"message": "Global delta sync completed."})
    except Exception as e:
        logger.error(f"Error in delta sync: {e}")
        return jsonify({"error": str(e)}), 500

@app.route("/dashboard")
def dashboard():
    return render_template('dashboard.html')

# Scheduler Setup with Job IDs
scheduler = BackgroundScheduler()
scheduler.add_job(refresh_top_n_tickers, "interval", minutes=LATEST_CACHE_REFRESH_INTERVAL_MINUTES, id="cache_refresh")
scheduler.add_job(delta_sync, "interval", days=DELTA_SYNC_INTERVAL_DAYS, id="delta_sync")
scheduler.add_job(save_query_counter, "interval", minutes=QUERY_COUNTER_SAVE_INTERVAL_MINUTES, id="save_query_counter")
scheduler.start()

# Load query_counter on startup
load_query_counter()

if __name__ == "__main__":
    session = Session()
    quotes_count = session.query(StockQuote).count()
    session.close()
    if quotes_count == 0:
        logger.info("Database is empty. Running full sync...")
        full_sync()
    logger.info(f"Starting Flask API on {FLASK_HOST}:{FLASK_PORT}...")
    app.run(host=FLASK_HOST, port=FLASK_PORT)
