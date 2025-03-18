import datetime
import time
import logging

import pandas as pd
import yfinance as yf
from yfinance import EquityQuery
from flask import Flask, jsonify, request
from sqlalchemy import (BigInteger, Column, Date, DateTime, DECIMAL, ForeignKey,
                        Integer, String, create_engine)
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker
from apscheduler.schedulers.background import BackgroundScheduler

# ====================================================
# Logging Configuration
# ====================================================
logging.basicConfig(level=logging.INFO,  # Set to DEBUG to see detailed messages
                    format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# ====================================================
# Configurable Parameters
# ====================================================
# Data Fetching Parameters
MAX_TICKERS_PER_REQUEST = 50        # Maximum tickers per request for historical data and cache refresh
REQUEST_DELAY_SECONDS = 5           # Delay between batch requests (in seconds)
HISTORICAL_START_DATE = "2020-01-01"  # Start date for historical data fetching
YFINANCE_REGION = "th"              # Region for Thailand stocks

# Database Configuration
DATABASE_URL = "sqlite:///instance/stock_data.db"  # Database connection string

# API Server Configuration
FLASK_HOST = "0.0.0.0"
FLASK_PORT = 8080

# Scheduler Job Intervals
LATEST_CACHE_REFRESH_INTERVAL_MINUTES = 5  # In-memory cache refresh interval (in minutes)
DELTA_SYNC_INTERVAL_DAYS = 1               # Delta sync job interval (in days)

# ====================================================
# Database Models & Setup
# ====================================================
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
    id = Column(Integer, primary_key=True)  # Single row (id=1)
    last_sync = Column(DateTime)


# Create engine and session
engine = create_engine(DATABASE_URL, echo=False)
Base.metadata.create_all(engine)
Session = sessionmaker(bind=engine)

# ====================================================
# In-Memory Latest Price Cache
# ====================================================
latest_cache = {}

# ====================================================
# Helper Functions
# ====================================================
def safe_convert(value, convert_func=lambda x: x):
    """
    Returns the converted value using convert_func if value is not NaN or None.
    Otherwise, returns None.
    """
    if value is None or pd.isna(value):
        return None
    try:
        return convert_func(value)
    except Exception:
        return None

def chunk_list(lst, chunk_size):
    """
    Yield successive chunks of size chunk_size from lst.
    This function is used to process tickers in batches.
    """
    for i in range(0, len(lst), chunk_size):
        yield lst[i:i + chunk_size]

# ====================================================
# Data Fetching Functions
# ====================================================
def fetch_yf_data(max_tickers_per_request, delay_t, query, start_date=HISTORICAL_START_DATE, end_date=None, sample_size=None):
    """
    Fetch quotes and historical price data from yfinance.
    If sample_size is provided, fetch only that many quotes.
    Otherwise, fetch quotes in batches.
    """
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
    processed_since_pause = 0  # Counter to track tickers processed since the last pause

    # Process tickers in batches using the chunk_list helper
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
            # Single ticker downloaded
            ticker = batch_symbols[0]
            historical_data[ticker] = data
            logger.debug(f"Historical data fetched for single ticker: {ticker}")

        processed_since_pause += len(batch_symbols)
        # Pause for 60 seconds if 1000 or more tickers have been processed since the last pause
        if processed_since_pause >= 1000:
            logger.info(f"Processed {processed_since_pause} tickers since last pause, pausing for 60 seconds to avoid rate limits.")
            time.sleep(60)
            processed_since_pause = 0
        else:
            time.sleep(delay_t)

    logger.info("Completed fetching historical data.")
    return quotes_df, historical_data

def update_database(quotes_df, historical_data, upsert=False):
    """
    Update StockQuote and StockPrice tables.
    
    - For a full sync (upsert=False), use bulk_insert_mappings (after clearing or replacing data).
    - For delta sync (upsert=True), perform an upsert via session.merge() so that existing rows are updated.
    """
    session = Session()

    # Prepare bulk data for StockQuote
    logger.info("Preparing data for StockQuote table...")
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
        logger.info("Performing upsert (merge) for StockQuote records...")
        for mapping in stock_quote_mappings:
            # session.merge() will update the existing record if it exists or insert a new one if not.
            session.merge(StockQuote(**mapping))
        session.commit()
        logger.info(f"Upserted {len(stock_quote_mappings)} StockQuote records.")
    else:
        # Optionally clear tables if doing a full sync
        # session.query(StockPrice).delete()
        # session.query(StockQuote).delete()
        # session.commit()
        logger.info("Bulk inserting StockQuote records...")
        session.bulk_insert_mappings(StockQuote, stock_quote_mappings)
        session.commit()
        logger.info(f"Inserted {len(stock_quote_mappings)} StockQuote records.")

    # Prepare data for StockPrice
    logger.info("Preparing data for StockPrice table...")
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
        logger.info("Performing upsert (merge) for StockPrice records...")
        for mapping in stock_price_mappings:
            session.merge(StockPrice(**mapping))
        session.commit()
        logger.info(f"Upserted {len(stock_price_mappings)} StockPrice records.")
    else:
        logger.info("Bulk inserting StockPrice records...")
        session.bulk_insert_mappings(StockPrice, stock_price_mappings)
        session.commit()
        logger.info(f"Inserted {len(stock_price_mappings)} StockPrice records.")

    session.close()

# ====================================================
# Sync Job Functions
# ====================================================
def full_sync():
    """
    Full Sync: Fetch all historical data from HISTORICAL_START_DATE to the latest available date.
    Also update the StockQuote metadata using bulk insertion.
    Now fetches both Thailand and US stocks.
    """
    logger.info("Starting Full Sync...")

    # Query for Thailand stocks
    query_th = EquityQuery("eq", ["region", YFINANCE_REGION])
    quotes_df_th, historical_data_th = fetch_yf_data(
        max_tickers_per_request=MAX_TICKERS_PER_REQUEST,
        delay_t=REQUEST_DELAY_SECONDS,
        query=query_th,
        start_date=HISTORICAL_START_DATE,
    )

    # Query for US stocks
    query_us = EquityQuery("is-in", ["exchange", "NMS", "NYQ"])
    quotes_df_us, historical_data_us = fetch_yf_data(
        max_tickers_per_request=MAX_TICKERS_PER_REQUEST,
        delay_t=REQUEST_DELAY_SECONDS,
        query=query_us,
        start_date=HISTORICAL_START_DATE,
    )

    # Combine results from both queries
    quotes_df = pd.concat([quotes_df_th, quotes_df_us], ignore_index=True)
    historical_data = {**historical_data_th, **historical_data_us}
    logger.info(f"Total combined tickers: {len(quotes_df)}")

    update_database(quotes_df, historical_data, upsert=False)
    session = Session()
    state = session.query(DeltaSyncState).filter_by(id=1).first()
    if not state:
        state = DeltaSyncState(id=1)
    state.last_sync = datetime.datetime.now()
    session.merge(state)
    session.commit()
    session.close()
    logger.info("Full Sync Completed.")

def delta_sync():
    """
    Delta Sync: Update the database with the latest data for the past two days.
    This uses upsert (via session.merge) so that existing rows are updated if needed.
    Now fetches both Thailand and US stocks.
    """
    logger.info("Starting Delta Sync...")
    session = Session()
    state = session.query(DeltaSyncState).filter_by(id=1).first()
    last_sync = state.last_sync if state else None
    session.close()

    today = datetime.datetime.now().date()
    two_days_ago = today - datetime.timedelta(days=2)

    # Query for Thailand stocks
    query_th = EquityQuery("eq", ["region", YFINANCE_REGION])
    quotes_df_th, historical_data_th = fetch_yf_data(
        max_tickers_per_request=MAX_TICKERS_PER_REQUEST,
        delay_t=REQUEST_DELAY_SECONDS,
        query=query_th,
        start_date=two_days_ago.strftime("%Y-%m-%d"),
        end_date=today.strftime("%Y-%m-%d"),
    )

    # Query for US stocks
    query_us = EquityQuery("is-in", ["exchange", "NMS", "NYQ"])
    quotes_df_us, historical_data_us = fetch_yf_data(
        max_tickers_per_request=MAX_TICKERS_PER_REQUEST,
        delay_t=REQUEST_DELAY_SECONDS,
        query=query_us,
        start_date=two_days_ago.strftime("%Y-%m-%d"),
        end_date=today.strftime("%Y-%m-%d"),
    )

    # Combine results from both queries
    quotes_df = pd.concat([quotes_df_th, quotes_df_us], ignore_index=True)
    historical_data = {**historical_data_th, **historical_data_us}
    logger.info(f"Total combined tickers for delta sync: {len(quotes_df)}")

    update_database(quotes_df, historical_data, upsert=True)
    session = Session()
    state = session.query(DeltaSyncState).filter_by(id=1).first()
    if not state:
        state = DeltaSyncState(id=1)
    state.last_sync = datetime.datetime.now()
    session.merge(state)
    session.commit()
    session.close()
    logger.info("Delta Sync Completed.")

# ====================================================
# Latest Cache Refresh Function
# ====================================================
def refresh_latest_cache():
    """
    Refresh the in-memory latest price cache.
    Query the StockQuote table for all tickers, then use yfinance to fetch the current price for each in batches.
    """
    logger.info("Refreshing latest cache...")
    session = Session()
    tickers = [row.ticker for row in session.query(StockQuote.ticker).all()]
    session.close()
    total_tickers = len(tickers)
    logger.info(f"Found {total_tickers} tickers in database for cache refresh.")

    new_cache = {}
    for batch_tickers in chunk_list(tickers, MAX_TICKERS_PER_REQUEST):
        tickers_str = " ".join(batch_tickers)
        logger.info(f"Fetching latest prices for batch: {batch_tickers}")
        try:
            data = yf.Tickers(tickers_str)
            for ticker in batch_tickers:
                try:
                    last_price = data.tickers[ticker].fast_info["last_price"]
                    new_cache[ticker] = last_price
                    logger.debug(f"Ticker {ticker}: last price fetched as {last_price}")
                except Exception as e:
                    logger.error(f"Error fetching latest price for {ticker}: {e}")
        except Exception as e:
            logger.error(f"Error fetching batch for tickers {batch_tickers}: {e}")
        time.sleep(REQUEST_DELAY_SECONDS)
    global latest_cache
    latest_cache = new_cache
    logger.info(f"Latest cache refreshed for {len(new_cache)} tickers out of {total_tickers}.")

# ====================================================
# Flask API Endpoints
# ====================================================
app = Flask(__name__)

@app.route("/api/latest")
def get_latest():
    ticker = request.args.get("ticker")
    if not ticker:
        return jsonify({"error": "Ticker parameter is required"}), 400
    if ticker in latest_cache:
        return jsonify({ticker: latest_cache[ticker]})
    else:
        return jsonify({"error": "Ticker not found in latest cache"}), 404

@app.route("/api/assets")
def get_assets():
    session = Session()
    quotes = session.query(StockQuote).all()
    session.close()
    assets = []
    for quote in quotes:
        assets.append(
            {
                "ticker": quote.ticker,
                "long_name": quote.long_name,
                "short_name": quote.short_name,
                "region": quote.region,
                "exchange": quote.exchange,
            }
        )
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
    total_volume = 0
    count = 0
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
        if price.volume:
            total_volume += price.volume
            count += 1
    average_volume = total_volume / count if count > 0 else None
    response = {"ticker": ticker, "historical_data": data, "average_volume": average_volume}
    return jsonify(response)

# ====================================================
# Scheduler Setup
# ====================================================
scheduler = BackgroundScheduler()
scheduler.add_job(refresh_latest_cache, "interval", minutes=LATEST_CACHE_REFRESH_INTERVAL_MINUTES)
scheduler.add_job(delta_sync, "interval", days=DELTA_SYNC_INTERVAL_DAYS)
scheduler.start()

# ====================================================
# Main Entry Point
# ====================================================
if __name__ == "__main__":
    # Run a full sync if the database is empty.
    session = Session()
    quotes_count = session.query(StockQuote).count()
    session.close()
    if quotes_count == 0:
        logger.info("Database is empty. Running full sync...")
        full_sync()
    # Start the Flask API
    logger.info(f"Starting Flask API on {FLASK_HOST}:{FLASK_PORT}...")
    app.run(host=FLASK_HOST, port=FLASK_PORT)
