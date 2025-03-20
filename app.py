import datetime
import time
import logging
import os
from collections import Counter
from flask import Flask, jsonify, request, render_template
from sqlalchemy import BigInteger, Column, Date, DateTime, DECIMAL, Integer, String, create_engine, func, text
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker
from apscheduler.schedulers.background import BackgroundScheduler
import pandas as pd
import yfinance as yf
import requests
from decimal import Decimal

# Logging Configuration
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# Configurable Parameters
MAX_TICKERS_PER_REQUEST = 50
REQUEST_DELAY_SECONDS = 5
HISTORICAL_START_DATE = "2020-01-01"
DATABASE_URL = "sqlite:///instance/stock_data.db"
FLASK_HOST = "0.0.0.0"
FLASK_PORT = 8082
TOP_N_TICKERS = 100  # Number of top tickers to refresh periodically
LATEST_CACHE_REFRESH_INTERVAL_MINUTES = 1  # Refresh interval for top tickers
REGULAR_TTL = 15  # minutes, for existing tickers
NOT_FOUND_TTL = 1440  # minutes (24 hours), for non-existent tickers
QUERY_COUNTER_SAVE_INTERVAL_MINUTES = 5  # Save query counter every 5 minutes
DELTA_SYNC_INTERVAL_DAYS = 1  # Delta sync interval (default daily)

# Global variable to track last cache refresh
last_cache_refresh = None

# SQLAlchemy Setup and Models
Base = declarative_base()

# Shared base model for metadata using inheritance
class BaseQuote(Base):
    __abstract__ = True
    ticker = Column(String(50), primary_key=True)  # For stocks: symbol; for crypto: CoinGecko coin id
    asset_type = Column(String(10), nullable=False, primary_key=True)  # 'STOCK' or 'CRYPTO'
    symbol = Column(String(20), nullable=False)
    name = Column(String(100), nullable=True)

# Stock Quote Model – includes stock-specific static fields
class StockQuote(BaseQuote):
    __tablename__ = "stock_quotes"
    language = Column(String(10))
    region = Column(String(10))
    quote_type = Column(String(20))
    exchange = Column(String(50))
    full_exchange_name = Column(String(100))
    first_trade_date = Column(Date)

# Crypto Quote Model – includes only static fields from CoinGecko metadata
class CryptoQuote(BaseQuote):
    __tablename__ = "crypto_quotes"
    image = Column(String(200))
    ath = Column(DECIMAL(15, 2))         # All-time high price
    ath_date = Column(DateTime)
    atl = Column(DECIMAL(15, 2))         # All-time low price
    atl_date = Column(DateTime)
    total_supply = Column(BigInteger)    # Generally static
    max_supply = Column(BigInteger)

# Unified Price Model for historical data (for both stocks and crypto)
class AssetPrice(Base):
    __tablename__ = "asset_prices"
    ticker = Column(String(50), primary_key=True)
    asset_type = Column(String(10), primary_key=True)
    price_date = Column(Date, primary_key=True)
    open_price = Column(DECIMAL(10, 2))
    high_price = Column(DECIMAL(10, 2))
    low_price = Column(DECIMAL(10, 2))
    close_price = Column(DECIMAL(10, 2))
    volume = Column(DECIMAL(20, 8))  # Changed to DECIMAL for precision

class DeltaSyncState(Base):
    __tablename__ = "delta_sync_state"
    id = Column(Integer, primary_key=True)
    last_full_sync = Column(DateTime)
    last_delta_sync = Column(DateTime)

# QueryCount with composite key for asset_type and ticker
class QueryCount(Base):
    __tablename__ = "query_counts"
    ticker = Column(String(50), primary_key=True)
    asset_type = Column(String(10), primary_key=True)
    count = Column(Integer, default=0)

# Create engine and session
engine = create_engine(DATABASE_URL, echo=False)
Base.metadata.create_all(engine)
Session = sessionmaker(bind=engine)

# Add missing columns for SQLite if necessary
with engine.connect() as conn:
    try:
        conn.execute(text("ALTER TABLE delta_sync_state ADD COLUMN last_full_sync DATETIME"))
    except Exception:
        pass
    try:
        conn.execute(text("ALTER TABLE delta_sync_state ADD COLUMN last_delta_sync DATETIME"))
    except Exception:
        pass

# Global Cache and Query Counter
latest_cache = {}  # Format: { (asset_type, ticker): (price or "NOT_FOUND", timestamp) }
query_counter = Counter()  # Tracks query frequency with key (asset_type, ticker)

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

# Stock Data Fetching & Database Update (using yfinance)
def fetch_yf_data(max_tickers_per_request, delay_t, query, start_date=HISTORICAL_START_DATE, end_date=None, sample_size=None):
    logger.info("Starting data fetch from yfinance for stocks...")
    all_quotes = []
    offset = 0
    size = sample_size if sample_size is not None else 250
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
    logger.info(f"Total stock tickers to process: {len(symbols)}")
    historical_data = {}
    processed_since_pause = 0
    for batch_symbols in chunk_list(symbols, max_tickers_per_request):
        tickers_str = " ".join(batch_symbols)
        logger.info(f"Downloading historical stock data for tickers: {batch_symbols}")
        data = yf.download(tickers=tickers_str, start=start_date, end=end_date, interval="1d", group_by='ticker') if end_date else yf.download(tickers=tickers_str, start=start_date, interval="1d", group_by='ticker')
        if isinstance(data.columns, pd.MultiIndex):
            available_tickers = data.columns.get_level_values(0).unique().tolist()
            for ticker in batch_symbols:
                if ticker in available_tickers:
                    try:
                        ticker_data = data[ticker]
                        historical_data[ticker] = ticker_data
                    except Exception as e:
                        logger.error(f"Error processing ticker {ticker}: {e}")
        else:
            ticker = batch_symbols[0]
            historical_data[ticker] = data
        processed_since_pause += len(batch_symbols)
        if processed_since_pause >= 1000:
            time.sleep(60)
            processed_since_pause = 0
        else:
            time.sleep(delay_t)
    logger.info("Completed fetching historical stock data.")
    return quotes_df, historical_data

def update_stock_database(quotes_df, historical_data, upsert=False):
    session = Session()
    stock_quote_mappings = []
    for idx, row in quotes_df.iterrows():
        ticker = row.get("symbol")
        if not ticker:
            continue
        mapping = {
            "ticker": ticker,
            "asset_type": "STOCK",
            "symbol": ticker,
            "name": row.get("longName") or row.get("displayName") or ticker,
            "language": row.get("language"),
            "region": row.get("region"),
            "quote_type": row.get("quoteType"),
            "exchange": row.get("exchange"),
            "full_exchange_name": row.get("fullExchangeName"),
            "first_trade_date": safe_convert(row.get("firstTradeDateMilliseconds"), lambda x: datetime.datetime.fromtimestamp(x / 1000).date()),
        }
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
                "asset_type": "STOCK",
                "price_date": price_date,
                "open_price": safe_convert(data_row.get("Open"), float),
                "high_price": safe_convert(data_row.get("High"), float),
                "low_price": safe_convert(data_row.get("Low"), float),
                "close_price": safe_convert(data_row.get("Close"), float),
                "volume": safe_convert(data_row.get("Volume"), Decimal)
            }
            stock_price_mappings.append(mapping)
    if upsert:
        for mapping in stock_price_mappings:
            session.merge(AssetPrice(**mapping))
        session.commit()
    else:
        session.bulk_insert_mappings(AssetPrice, stock_price_mappings)
        session.commit()
    session.close()

def full_sync_stocks():
    logger.info("Starting Full Sync for Stocks...")
    query_th = yf.EquityQuery("eq", ["region", "th"])
    quotes_df_th, historical_data_th = fetch_yf_data(MAX_TICKERS_PER_REQUEST, REQUEST_DELAY_SECONDS, query_th, start_date=HISTORICAL_START_DATE)
    query_us = yf.EquityQuery("is-in", ["exchange", "NMS", "NYQ"])
    quotes_df_us, historical_data_us = fetch_yf_data(MAX_TICKERS_PER_REQUEST, REQUEST_DELAY_SECONDS, query_us, start_date=HISTORICAL_START_DATE)
    quotes_df = pd.concat([quotes_df_th, quotes_df_us], ignore_index=True)
    historical_data = {**historical_data_th, **historical_data_us}
    update_stock_database(quotes_df, historical_data, upsert=False)
    session = Session()
    state = session.query(DeltaSyncState).filter_by(id=1).first()
    if not state:
        state = DeltaSyncState(id=1)
    state.last_full_sync = datetime.datetime.now()
    session.merge(state)
    session.commit()
    session.close()
    logger.info("Full Sync for Stocks Completed.")

def delta_sync_stocks():
    logger.info("Starting Delta Sync for Stocks...")
    session = Session()
    state = session.query(DeltaSyncState).filter_by(id=1).first()
    session.close()
    today = datetime.datetime.now().date()
    two_days_ago = today - datetime.timedelta(days=2)
    query_th = yf.EquityQuery("eq", ["region", "th"])
    quotes_df_th, historical_data_th = fetch_yf_data(MAX_TICKERS_PER_REQUEST, REQUEST_DELAY_SECONDS, query_th, start_date=two_days_ago.strftime("%Y-%m-%d"), end_date=today.strftime("%Y-%m-%d"))
    query_us = yf.EquityQuery("is-in", ["exchange", "NMS", "NYQ"])
    quotes_df_us, historical_data_us = fetch_yf_data(MAX_TICKERS_PER_REQUEST, REQUEST_DELAY_SECONDS, query_us, start_date=two_days_ago.strftime("%Y-%m-%d"), end_date=today.strftime("%Y-%m-%d"))
    quotes_df = pd.concat([quotes_df_th, quotes_df_us], ignore_index=True)
    historical_data = {**historical_data_th, **historical_data_us}
    update_stock_database(quotes_df, historical_data, upsert=True)
    session = Session()
    state = session.query(DeltaSyncState).filter_by(id=1).first()
    if not state:
        state = DeltaSyncState(id=1)
    state.last_delta_sync = datetime.datetime.now()
    session.merge(state)
    session.commit()
    session.close()
    logger.info("Delta Sync for Stocks Completed.")

# Crypto Data Fetching & Database Update
def fetch_coingecko_data():
    logger.info("Fetching crypto metadata from CoinGecko...")
    url = "https://api.coingecko.com/api/v3/coins/markets"
    params = {
        "vs_currency": "usd",
        "order": "market_cap_desc",
        "per_page": 250,
        "page": 1,
        "sparkline": "false"
    }
    headers = {"accept": "application/json"}
    try:
        response = requests.get(url, params=params, headers=headers)
        if response.status_code == 200:
            data = response.json()
            logger.info(f"Fetched metadata for {len(data)} cryptocurrencies.")
            return data
        else:
            logger.error("Error fetching crypto metadata: " + response.text)
            return []
    except Exception as e:
        logger.error("Exception fetching crypto metadata: " + str(e))
        return []

def update_crypto_database(crypto_data, historical_data, upsert=False):
    session = Session()
    crypto_quote_mappings = []
    for coin in crypto_data:
        mapping = {
            "ticker": coin.get("id"),
            "asset_type": "CRYPTO",
            "symbol": coin.get("symbol"),
            "name": coin.get("name"),
            "image": coin.get("image"),
            "ath": safe_convert(coin.get("ath"), float),
            "ath_date": pd.to_datetime(coin.get("ath_date")) if coin.get("ath_date") else None,
            "atl": safe_convert(coin.get("atl"), float),
            "atl_date": pd.to_datetime(coin.get("atl_date")) if coin.get("atl_date") else None,
            "total_supply": safe_convert(coin.get("total_supply"), int),
            "max_supply": safe_convert(coin.get("max_supply"), int)
        }
        crypto_quote_mappings.append(mapping)
    if upsert:
        for mapping in crypto_quote_mappings:
            session.merge(CryptoQuote(**mapping))
        session.commit()
    else:
        session.bulk_insert_mappings(CryptoQuote, crypto_quote_mappings)
        session.commit()
    crypto_price_mappings = []
    for ticker, df in historical_data.items():
        if df is None or df.empty:
            continue
        for date, data_row in df.iterrows():
            price_date = date.date() if isinstance(date, datetime.datetime) else date
            mapping = {
                "ticker": ticker,
                "asset_type": "CRYPTO",
                "price_date": price_date,
                "open_price": safe_convert(data_row.get("open"), float),
                "high_price": safe_convert(data_row.get("high"), float),
                "low_price": safe_convert(data_row.get("low"), float),
                "close_price": safe_convert(data_row.get("close"), float),
                "volume": safe_convert(data_row.get("volume"), Decimal)
            }
            crypto_price_mappings.append(mapping)
    if upsert:
        for mapping in crypto_price_mappings:
            session.merge(AssetPrice(**mapping))
        session.commit()
    else:
        session.bulk_insert_mappings(AssetPrice, crypto_price_mappings)
        session.commit()
    session.close()

def full_sync_crypto():
    logger.info("Starting Full Sync for Cryptocurrencies...")
    crypto_data = fetch_coingecko_data()
    historical_data = {}
    for coin in crypto_data:
        coin_id = coin.get("id")
        coin_symbol = coin.get("symbol").upper() + "USDT"
        logger.info(f"Fetching historical crypto data for {coin_symbol}...")
        df = fetch_binance_crypto_data(coin_symbol, HISTORICAL_START_DATE, None)
        historical_data[coin_id] = df
        time.sleep(REQUEST_DELAY_SECONDS)
    update_crypto_database(crypto_data, historical_data, upsert=False)
    session = Session()
    state = session.query(DeltaSyncState).filter_by(id=1).first()
    if not state:
        state = DeltaSyncState(id=1)
    state.last_full_sync = datetime.datetime.now()
    session.merge(state)
    session.commit()
    session.close()
    logger.info("Full Sync for Cryptocurrencies Completed.")

def delta_sync_crypto():
    logger.info("Starting Delta Sync for Cryptocurrencies...")
    session = Session()
    state = session.query(DeltaSyncState).filter_by(id=1).first()
    session.close()
    today = datetime.datetime.now().date()
    two_days_ago = today - datetime.timedelta(days=2)
    crypto_data = fetch_coingecko_data()
    historical_data = {}
    for coin in crypto_data:
        coin_id = coin.get("id")
        coin_symbol = coin.get("symbol").upper() + "USDT"
        logger.info(f"Fetching delta crypto data for {coin_symbol}...")
        df = fetch_binance_crypto_data(coin_symbol, two_days_ago.strftime("%Y-%m-%d"), today.strftime("%Y-%m-%d"))
        historical_data[coin_id] = df
        time.sleep(REQUEST_DELAY_SECONDS)
    update_crypto_database(crypto_data, historical_data, upsert=True)
    session = Session()
    state = session.query(DeltaSyncState).filter_by(id=1).first()
    if not state:
        state = DeltaSyncState(id=1)
    state.last_delta_sync = datetime.datetime.now()
    session.merge(state)
    session.commit()
    session.close()
    logger.info("Delta Sync for Cryptocurrencies Completed.")

# Binance API helper for fetching crypto historical data
BASE_BINANCE_URL = "https://api.binance.com"

def safe_get(url, params=None, max_retries=5):
    for attempt in range(max_retries):
        try:
            response = requests.get(url, params=params, timeout=10)
        except Exception as e:
            logger.error(f"Request error: {e}")
            time.sleep(1)
            continue
        if response.status_code == 200:
            return response
        elif response.status_code in (429, 418):
            retry_after = int(response.headers.get("Retry-After", "1"))
            logger.warning(f"Rate limit hit (HTTP {response.status_code}). Retrying after {retry_after} seconds...")
            time.sleep(retry_after)
        else:
            logger.error(f"Error: HTTP {response.status_code} - {response.text}")
            response.raise_for_status()
    raise Exception("Max retries exceeded for URL: " + url)

def fetch_binance_crypto_data(symbol, start_date, end_date):
    logger.info(f"Fetching Binance historical data for {symbol}...")
    try:
        if start_date:
            start_ts = int(datetime.datetime.strptime(start_date, "%Y-%m-%d").timestamp() * 1000)
        else:
            start_ts = int(datetime.datetime.now().timestamp() * 1000) - (5 * 365 * 24 * 60 * 60 * 1000)
        if end_date:
            end_ts = int(datetime.datetime.strptime(end_date, "%Y-%m-%d").timestamp() * 1000)
        else:
            end_ts = int(datetime.datetime.now().timestamp() * 1000)
    except Exception as e:
        logger.error(f"Error processing dates for symbol {symbol}: {e}")
        return pd.DataFrame()

    limit = 1000
    klines = []
    current_start = start_ts
    url = BASE_BINANCE_URL + "/api/v3/klines"
    
    while current_start < end_ts:
        try:
            params = {
                "symbol": symbol,
                "interval": "1d",
                "startTime": current_start,
                "endTime": end_ts,
                "limit": limit
            }
            response = safe_get(url, params=params)
            data = response.json()
        except Exception as e:
            logger.error(f"Error fetching data for symbol {symbol} starting at {current_start}: {e}")
            break
        
        if not data:
            break
        
        klines.extend(data)
        last_time = data[-1][0]
        if last_time == current_start:
            break
        current_start = last_time + 1
        time.sleep(0.1)
    
    if not klines:
        return pd.DataFrame()
    
    try:
        df = pd.DataFrame(klines, columns=["open_time", "open", "high", "low", "close", "volume", "close_time",
                                           "quote_asset_volume", "num_trades", "taker_buy_base", "taker_buy_quote", "ignore"])
        df["open_time"] = pd.to_datetime(df["open_time"], unit='ms')
        df.set_index("open_time", inplace=True)
        df = df.astype({"open": "float", "high": "float", "low": "float", "close": "float", "volume": "float"})
    except Exception as e:
        logger.error(f"Error processing DataFrame for symbol {symbol}: {e}")
        return pd.DataFrame()
    
    return df

# Data Source Classes for Latest Price Fetch
class StockDataSource:
    @staticmethod
    def get_latest_price(ticker):
        try:
            data = yf.Ticker(ticker)
            return data.fast_info["last_price"]
        except KeyError:
            return "NOT_FOUND"  # Ticker does not exist
        except Exception as e:
            logger.error(f"Error fetching latest price for stock {ticker}: {e}")
            return None  # Other errors (e.g., network)

    @staticmethod
    def refresh_latest_prices(tickers):
        prices = {}
        try:
            tickers_str = " ".join(tickers)
            data = yf.Tickers(tickers_str)
            for ticker in tickers:
                try:
                    price = data.tickers[ticker].fast_info["last_price"]
                    prices[ticker] = price
                except KeyError:
                    prices[ticker] = "NOT_FOUND"
                except Exception as e:
                    logger.error(f"Error fetching latest price for stock {ticker}: {e}")
            return prices
        except Exception as e:
            logger.error(f"Error fetching batch latest prices for stocks: {e}")
            return {}

class CryptoDataSource:
    BASE_URL = "https://api.coingecko.com/api/v3"
    
    @staticmethod
    def get_all_latest_prices():
        url = f"{CryptoDataSource.BASE_URL}/coins/markets"
        params = {
            "vs_currency": "usd",
            "order": "market_cap_desc",
            "per_page": 250,
            "page": 1,
            "sparkline": "false"
        }
        headers = {"accept": "application/json"}
        try:
            response = requests.get(url, params=params, headers=headers)
            if response.status_code == 200:
                data = response.json()
                return {coin["id"]: coin["current_price"] for coin in data}
            else:
                logger.error("Error fetching crypto latest prices: " + response.text)
                return {}
        except Exception as e:
            logger.error("Error fetching crypto latest prices: " + str(e))
            return {}
    
    @staticmethod
    def get_latest_price(ticker):
        prices = CryptoDataSource.get_all_latest_prices()
        return prices.get(ticker, "NOT_FOUND")

# Global latest price function (delegates by asset_type)
def get_latest_price(ticker, asset_type="STOCK"):
    key = (asset_type.upper(), ticker)
    query_counter[key] += 1
    now = datetime.datetime.now()
    
    # Check cache
    if key in latest_cache:
        value, timestamp = latest_cache[key]
        if value == "NOT_FOUND":
            if (now - timestamp).total_seconds() / 60 < NOT_FOUND_TTL:
                return "NOT_FOUND"
        elif value is not None:
            if (now - timestamp).total_seconds() / 60 < REGULAR_TTL:
                return value
    
    # Fetch from data source
    if asset_type.upper() == "STOCK":
        price = StockDataSource.get_latest_price(ticker)
    else:
        price = CryptoDataSource.get_latest_price(ticker)
    
    # Update cache and return
    if price == "NOT_FOUND":
        latest_cache[key] = ("NOT_FOUND", now)
        return "NOT_FOUND"
    elif price is not None:
        latest_cache[key] = (price, now)
        return price
    else:
        # Error fetching (e.g., network issue)
        if key in latest_cache:
            value, _ = latest_cache[key]
            if value != "NOT_FOUND":
                return value  # Fallback to expired price if not "NOT_FOUND"
        return "FETCH_ERROR"

def refresh_stock_top_n_tickers():
    top_tickers = [ticker for (atype, ticker), _ in query_counter.most_common(TOP_N_TICKERS) if atype == "STOCK"]
    for batch in chunk_list(top_tickers, MAX_TICKERS_PER_REQUEST):
        prices = StockDataSource.refresh_latest_prices(batch)
        now = datetime.datetime.now()
        for ticker, price in prices.items():
            key = ("STOCK", ticker)
            latest_cache[key] = (price, now)  # Cache "NOT_FOUND" or price
        time.sleep(REQUEST_DELAY_SECONDS)
    logger.info(f"Refreshed latest prices for {len(top_tickers)} stock tickers.")

def refresh_crypto_prices():
    top_tickers = [ticker for (atype, ticker), _ in query_counter.most_common(TOP_N_TICKERS) if atype == "CRYPTO"]
    if not top_tickers:
        return
    prices = CryptoDataSource.get_all_latest_prices()
    now = datetime.datetime.now()
    for ticker in top_tickers:
        price = prices.get(ticker, "NOT_FOUND")
        key = ("CRYPTO", ticker)
        latest_cache[key] = (price, now)
    logger.info(f"Refreshed latest prices for {len(top_tickers)} crypto tickers.")

def refresh_all_latest_prices():
    refresh_stock_top_n_tickers()
    refresh_crypto_prices()
    global last_cache_refresh
    last_cache_refresh = datetime.datetime.now()

# Save and Load Query Counter
def save_query_counter():
    session = Session()
    for (ticker, asset_type), count in query_counter.items():
        existing = session.query(QueryCount).filter_by(ticker=ticker, asset_type=asset_type).first()
        if existing:
            existing.count += count
        else:
            session.add(QueryCount(ticker=ticker, asset_type=asset_type, count=count))
    session.commit()
    session.close()
    logger.info("Saved query_counter to database.")

def load_query_counter():
    session = Session()
    query_counts = session.query(QueryCount).all()
    for qc in query_counts:
        query_counter[(qc.ticker, qc.asset_type)] = qc.count
    session.close()
    logger.info("Loaded query_counter from database.")

# Flask API Endpoints and Dashboard
app = Flask(__name__)
api_stats = Counter()

@app.route("/api/unified")
def get_unified_ticker():
    ticker = request.args.get("ticker")
    asset_type = request.args.get("asset_type", "STOCK").upper()
    if not ticker:
        return jsonify({"error": "Ticker parameter is required"}), 400
    session = Session()
    if asset_type == "CRYPTO":
        quote = session.query(CryptoQuote).filter_by(ticker=ticker, asset_type=asset_type).first()
    else:
        quote = session.query(StockQuote).filter_by(ticker=ticker, asset_type=asset_type).first()
    prices = session.query(AssetPrice).filter_by(ticker=ticker, asset_type=asset_type).all()
    session.close()
    if not quote:
        return jsonify({"error": "Ticker not found"}), 404
    quote_data = {
        "ticker": quote.ticker,
        "asset_type": asset_type,
        "symbol": quote.symbol,
        "name": quote.name
    }
    if asset_type == "STOCK":
        quote_data.update({
            "language": quote.language,
            "region": quote.region,
            "quote_type": quote.quote_type,
            "exchange": quote.exchange,
            "full_exchange_name": quote.full_exchange_name,
            "first_trade_date": quote.first_trade_date.strftime("%Y-%m-%d") if quote.first_trade_date else None,
        })
    else:
        quote_data.update({
            "image": quote.image,
            "ath": float(quote.ath) if quote.ath is not None else None,
            "ath_date": quote.ath_date.isoformat() if quote.ath_date else None,
            "atl": float(quote.atl) if quote.atl is not None else None,
            "atl_date": quote.atl_date.isoformat() if quote.atl_date else None,
            "total_supply": quote.total_supply,
            "max_supply": quote.max_supply,
        })
    key = (asset_type, ticker)
    cache_entry = latest_cache.get(key, (None, None))
    latest_cache_data = {
        "price": cache_entry[0],
        "timestamp": cache_entry[1].isoformat() if cache_entry[1] else None
    }
    unified_data = {
        "ticker": ticker,
        "asset_type": asset_type,
        "quote_data": quote_data,
        "latest_cache": latest_cache_data,
        "historical_data": [
            {
                "date": price.price_date.strftime("%Y-%m-%d"),
                "open": float(price.open_price) if price.open_price is not None else None,
                "high": float(price.high_price) if price.high_price is not None else None,
                "low": float(price.low_price) if price.low_price is not None else None,
                "close": float(price.close_price) if price.close_price is not None else None,
                "volume": float(price.volume) if price.volume is not None else None,
            }
            for price in prices
        ]
    }
    return jsonify(unified_data)

@app.route("/api/data_quality")
def data_quality():
    session = Session()
    total_stock_tickers = session.query(StockQuote).count()
    total_crypto_tickers = session.query(CryptoQuote).count()
    missing_long_name_stock = session.query(StockQuote).filter(StockQuote.name.is_(None)).count()
    missing_exchange_stock = session.query(StockQuote).filter(StockQuote.exchange.is_(None)).count()
    duplicate_entries = 0
    duplicates = session.query(
        AssetPrice.ticker, AssetPrice.asset_type, func.count(AssetPrice.ticker).label("dup_count")
    ).group_by(AssetPrice.ticker, AssetPrice.asset_type).having(func.count(AssetPrice.ticker) > 1).all()
    for dup in duplicates:
        duplicate_entries += dup.dup_count - 1
    session.close()
    data_quality_metrics = {
        "total_stock_tickers": total_stock_tickers,
        "total_crypto_tickers": total_crypto_tickers,
        "missing_fields": missing_long_name_stock + missing_exchange_stock,
        "duplicates": duplicate_entries
    }
    return jsonify(data_quality_metrics)

@app.route("/api/ticker_traffic")
def ticker_traffic():
    data = [{"ticker": t[1], "asset_type": t[0], "count": count} for (t, count) in query_counter.items()]
    return jsonify(data)

@app.route("/api/cache_info")
def cache_info():
    global last_cache_refresh
    cache_job = scheduler.get_job("cache_refresh")
    if cache_job and cache_job.next_run_time:
        now_aware = datetime.datetime.now(tz=cache_job.next_run_time.tzinfo)
        diff_seconds = (cache_job.next_run_time - now_aware).total_seconds()
        next_cache_refresh = f"{int(diff_seconds // 60)} minutes" if diff_seconds >= 60 else f"{int(diff_seconds)} seconds"
    else:
        next_cache_refresh = "N/A"
    return jsonify({
        "last_cache_refresh": last_cache_refresh.isoformat() if last_cache_refresh else None,
        "next_cache_refresh": next_cache_refresh
    })

@app.before_request
def before_request():
    if request.path.startswith('/api/'):
        key = request.path + "_" + request.args.get("ticker", "") + "_" + request.args.get("asset_type", "STOCK").upper()
        api_stats[key] += 1

@app.route("/api/latest")
def get_latest():
    ticker = request.args.get("ticker")
    asset_type = request.args.get("asset_type", "STOCK").upper()
    if not ticker:
        return jsonify({"error": "Ticker parameter is required"}), 400
    
    result = get_latest_price(ticker, asset_type)
    key = (asset_type, ticker)
    timestamp = latest_cache.get(key, (None, datetime.datetime.now()))[1]
    
    if isinstance(result, (int, float)):
        return jsonify({
            "ticker": ticker,
            "asset_type": asset_type,
            "price": result,
            "timestamp": timestamp.isoformat()
        })
    elif result == "NOT_FOUND":
        return jsonify({"error": "Ticker not found"}), 404
    else:  # "FETCH_ERROR"
        return jsonify({"error": "Unable to fetch latest price"}), 500

@app.route("/api/assets")
def get_assets():
    asset_type = request.args.get("asset_type", "STOCK").upper()
    session = Session()
    if asset_type == "CRYPTO":
        quotes = session.query(CryptoQuote).all()
    else:
        quotes = session.query(StockQuote).all()
    session.close()
    assets = []
    for quote in quotes:
        key = (asset_type, quote.ticker)
        latest = latest_cache.get(key, (None, None))
        assets.append({
            "ticker": quote.ticker,
            "asset_type": asset_type,
            "name": quote.name,
            "symbol": quote.symbol,
            "latest_price": latest[0],
            "updated_at": latest[1].isoformat() if latest[1] else None
        })
    return jsonify(assets)

@app.route("/api/historical")
def get_historical():
    ticker = request.args.get("ticker")
    asset_type = request.args.get("asset_type", "STOCK").upper()
    if not ticker:
        return jsonify({"error": "Ticker parameter is required"}), 400
    session = Session()
    prices = session.query(AssetPrice).filter_by(ticker=ticker, asset_type=asset_type).all()
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
            "volume": float(price.volume) if price.volume is not None else None,
        }
        data.append(record)
    return jsonify({"ticker": ticker, "asset_type": asset_type, "historical_data": data})

@app.route("/api/stats")
def get_stats():
    session = Session()
    total_stock_tickers = session.query(StockQuote).count()
    total_crypto_tickers = session.query(CryptoQuote).count()
    stock_prices_count = session.query(AssetPrice).filter_by(asset_type="STOCK").count()
    crypto_prices_count = session.query(AssetPrice).filter_by(asset_type="CRYPTO").count()
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
    
    db_file = 'instance/pricing_data.db'
    db_size = os.path.getsize(db_file) / (1024 * 1024)
    db_size_str = f"{db_size:.2f} MB" if db_size < 1024 else f"{db_size / 1024:.2f} GB"
    
    stats = {
        "total_stock_tickers": total_stock_tickers,
        "total_crypto_tickers": total_crypto_tickers,
        "db_size": db_size_str,
        "cache_hit_rate": "100%",  # Placeholder
        "api_requests_24h": sum(api_stats.values()),
        "table_records": {
            "stock_quotes": total_stock_tickers,
            "crypto_quotes": total_crypto_tickers,
            "asset_prices_stock": stock_prices_count,
            "asset_prices_crypto": crypto_prices_count,
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
    asset_type = data.get("asset_type", "STOCK").upper()
    try:
        if ticker:
            if asset_type == "CRYPTO":
                full_sync_crypto()
                return jsonify({"message": f"Full sync for crypto ticker {ticker} completed."})
            else:
                full_sync_stocks()
                return jsonify({"message": f"Full sync for stock ticker {ticker} completed."})
        else:
            if asset_type == "CRYPTO":
                full_sync_crypto()
                return jsonify({"message": "Global full sync for cryptocurrencies completed."})
            else:
                full_sync_stocks()
                return jsonify({"message": "Global full sync for stocks completed."})
    except Exception as e:
        logger.error(f"Error in full sync: {e}")
        return jsonify({"error": str(e)}), 500

@app.route("/api/sync/delta", methods=["POST"])
def sync_delta():
    data = request.get_json() or {}
    ticker = data.get("ticker")
    asset_type = data.get("asset_type", "STOCK").upper()
    try:
        if ticker:
            if asset_type == "CRYPTO":
                delta_sync_crypto()
                return jsonify({"message": f"Delta sync for crypto ticker {ticker} completed."})
            else:
                delta_sync_stocks()
                return jsonify({"message": f"Delta sync for stock ticker {ticker} completed."})
        else:
            if asset_type == "CRYPTO":
                delta_sync_crypto()
                return jsonify({"message": "Global delta sync for cryptocurrencies completed."})
            else:
                delta_sync_stocks()
                return jsonify({"message": "Global delta sync for stocks completed."})
    except Exception as e:
        logger.error(f"Error in delta sync: {e}")
        return jsonify({"error": str(e)}), 500

@app.route("/dashboard")
def dashboard():
    return render_template('dashboard.html')

# Scheduler Setup with Job IDs
scheduler = BackgroundScheduler()
scheduler.add_job(refresh_all_latest_prices, "interval", minutes=LATEST_CACHE_REFRESH_INTERVAL_MINUTES, id="cache_refresh")
scheduler.add_job(delta_sync_stocks, "interval", days=DELTA_SYNC_INTERVAL_DAYS, id="delta_sync_stocks")
scheduler.add_job(delta_sync_crypto, "interval", days=DELTA_SYNC_INTERVAL_DAYS, id="delta_sync_crypto")
scheduler.add_job(save_query_counter, "interval", minutes=QUERY_COUNTER_SAVE_INTERVAL_MINUTES, id="save_query_counter")
scheduler.start()

load_query_counter()

if __name__ == "__main__":
    session = Session()
    stock_quotes_count = session.query(StockQuote).count()
    crypto_quotes_count = session.query(CryptoQuote).count()
    session.close()
    if stock_quotes_count == 0 or crypto_quotes_count == 0:
        Base.metadata.drop_all(engine)
        Base.metadata.create_all(engine)
    if stock_quotes_count == 0:
        logger.info("Stock database is empty. Running full sync for stocks...")
        full_sync_stocks()
    if crypto_quotes_count == 0:
        logger.info("Crypto database is empty. Running full sync for cryptocurrencies...")
        full_sync_crypto()
    logger.info(f"Starting Flask API on {FLASK_HOST}:{FLASK_PORT}...")
    app.run(host=FLASK_HOST, port=FLASK_PORT)