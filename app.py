import datetime
import time
import logging
import os
import io
import pandas as pd
import requests
from collections import Counter
from decimal import Decimal
from flask import Flask, jsonify, request, render_template, current_app
from sqlalchemy import (BigInteger, Column, Date, DateTime, DECIMAL, Integer, String, create_engine, func, text,
                        ForeignKey, ForeignKeyConstraint)
from sqlalchemy.orm import sessionmaker, relationship, declarative_base
from sqlalchemy.exc import SQLAlchemyError
from apscheduler.schedulers.background import BackgroundScheduler
from rapidfuzz import fuzz

# ------------------------------------------------------------------------------
# Configurable Parameters
# ------------------------------------------------------------------------------
MAX_TICKERS_PER_REQUEST = 50
REQUEST_DELAY_SECONDS = 5
HISTORICAL_START_DATE = "2020-01-01"
DATABASE_URL = "sqlite:///instance/stock_data.db"
FLASK_HOST = "0.0.0.0"
FLASK_PORT = 8082
TOP_N_TICKERS = 100
LATEST_CACHE_REFRESH_INTERVAL_MINUTES = 1
REGULAR_TTL = 15
NOT_FOUND_TTL = 1440
QUERY_COUNTER_SAVE_INTERVAL_MINUTES = 5
DELTA_SYNC_INTERVAL_DAYS = 1

# New configuration for currency data (AlphaVantage)
ALPHAVANTAGE_API_KEY = "DB7QO6ZGF7BMMJCD"  # Replace with your own API key
CURRENCY_LIST_URL = "https://www.alphavantage.co/physical_currency_list/"

# ------------------------------------------------------------------------------
# Ensure the 'instance' directory exists
# ------------------------------------------------------------------------------
if not os.path.exists('instance'):
    os.makedirs('instance')

# ------------------------------------------------------------------------------
# Logging Configuration
# ------------------------------------------------------------------------------
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# ------------------------------------------------------------------------------
# Global Cache, Query Counter, and Baseline for last saved counts
# ------------------------------------------------------------------------------
latest_cache = {}  # key: (asset_quote.ticker) -> (price, timestamp)
query_counter = Counter()
last_saved_counts = {}  # holds the last saved count for each key
last_cache_refresh = None

# ------------------------------------------------------------------------------
# SQLAlchemy Setup and Models (New Database Design)
# ------------------------------------------------------------------------------
Base = declarative_base()

# ----- Asset & Specialized Asset Tables -----
class Asset(Base):
    __tablename__ = 'assets'
    # A composite primary key: (asset_type, symbol)
    asset_type = Column(String(10), primary_key=True)  # e.g. STOCK, CRYPTO, CURRENCY
    symbol = Column(String(20), primary_key=True)
    name = Column(String(100), nullable=True)
    discriminator = Column(String(50))  # used for polymorphic identity
    __mapper_args__ = {
        'polymorphic_on': discriminator,
        'polymorphic_identity': 'asset'
    }

class StockAsset(Asset):
    __tablename__ = 'stock_assets'
    asset_type = Column(String(10), ForeignKey('assets.asset_type'), primary_key=True)
    symbol = Column(String(20), ForeignKey('assets.symbol'), primary_key=True)
    exchange = Column(String(50))
    region = Column(String(10))
    language = Column(String(10))
    quote_type = Column(String(20))
    full_exchange_name = Column(String(100))
    first_trade_date = Column(Date)
    __mapper_args__ = {
        'polymorphic_identity': 'STOCK',
        # Explicit join condition to resolve ambiguity:
        'inherit_condition': (StockAsset.asset_type == Asset.asset_type) & (StockAsset.symbol == Asset.symbol)
    }

class CryptoAsset(Asset):
    __tablename__ = 'crypto_assets'
    asset_type = Column(String(10), ForeignKey('assets.asset_type'), primary_key=True)
    symbol = Column(String(20), ForeignKey('assets.symbol'), primary_key=True)
    image = Column(String(200))
    ath = Column(DECIMAL(15, 2))
    ath_date = Column(DateTime)
    atl = Column(DECIMAL(15, 2))
    atl_date = Column(DateTime)
    total_supply = Column(BigInteger)
    max_supply = Column(BigInteger)
    __mapper_args__ = {
        'polymorphic_identity': 'CRYPTO',
        'inherit_condition': (CryptoAsset.asset_type == Asset.asset_type) & (CryptoAsset.symbol == Asset.symbol)
    }

class CurrencyAsset(Asset):
    __tablename__ = 'currency_assets'
    asset_type = Column(String(10), ForeignKey('assets.asset_type'), primary_key=True)
    symbol = Column(String(20), ForeignKey('assets.symbol'), primary_key=True)
    __mapper_args__ = {
        'polymorphic_identity': 'CURRENCY',
        'inherit_condition': (CurrencyAsset.asset_type == Asset.asset_type) & (CurrencyAsset.symbol == Asset.symbol)
    }

# ----- AssetQuote: Represents a quote (price pairing) between two Assets -----
class AssetQuote(Base):
    __tablename__ = 'asset_quotes'
    # The ticker is derived from: from_asset.symbol + to_asset.symbol
    ticker = Column(String(50), primary_key=True)
    from_asset_type = Column(String(10))
    from_asset_symbol = Column(String(20))
    to_asset_type = Column(String(10))
    to_asset_symbol = Column(String(20))
    __table_args__ = (
        ForeignKeyConstraint(
            ['from_asset_type', 'from_asset_symbol'],
            ['assets.asset_type', 'assets.symbol']
        ),
        ForeignKeyConstraint(
            ['to_asset_type', 'to_asset_symbol'],
            ['assets.asset_type', 'assets.symbol']
        ),
    )
    from_asset = relationship("Asset", foreign_keys=[from_asset_type, from_asset_symbol])
    to_asset = relationship("Asset", foreign_keys=[to_asset_type, to_asset_symbol])

# ----- AssetPrice: Price data for a given AssetQuote from a specific DataSource -----
class AssetPrice(Base):
    __tablename__ = 'asset_prices'
    ticker = Column(String(50), primary_key=True)  # references AssetQuote.ticker
    price_datetime = Column(DateTime, primary_key=True)  # using datetime for precision
    data_source_id = Column(Integer, primary_key=True)  # foreign key to DataSource
    open_price = Column(DECIMAL(10, 2))
    high_price = Column(DECIMAL(10, 2))
    low_price = Column(DECIMAL(10, 2))
    close_price = Column(DECIMAL(10, 2))
    volume = Column(DECIMAL(20, 8))
    __table_args__ = (
        ForeignKeyConstraint(
            ['ticker'],
            ['asset_quotes.ticker']
        ),
    )

# ----- DataSource: Tracks the source of data (e.g. yFinance, Binance, AlphaVantage) -----
class DataSource(Base):
    __tablename__ = 'data_sources'
    id = Column(Integer, primary_key=True, autoincrement=True)
    name = Column(String(50), unique=True)
    description = Column(String(200), nullable=True)

# ----- DeltaSyncState & QueryCount -----
class DeltaSyncState(Base):
    __tablename__ = 'delta_sync_state'
    id = Column(Integer, primary_key=True)
    last_full_sync = Column(DateTime)
    last_delta_sync = Column(DateTime)

class QueryCount(Base):
    __tablename__ = 'query_counts'
    ticker = Column(String(50), primary_key=True)
    asset_type = Column(String(10), primary_key=True)
    count = Column(Integer, default=0)

# ------------------------------------------------------------------------------
# Create engine and session
# ------------------------------------------------------------------------------
engine = create_engine(DATABASE_URL, echo=False)
Base.metadata.create_all(engine)
Session = sessionmaker(bind=engine)

# (Optional) Add missing columns for SQLite if necessary
with engine.connect() as conn:
    try:
        conn.execute(text("ALTER TABLE delta_sync_state ADD COLUMN last_full_sync DATETIME"))
    except Exception:
        pass
    try:
        conn.execute(text("ALTER TABLE delta_sync_state ADD COLUMN last_delta_sync DATETIME"))
    except Exception:
        pass

# ------------------------------------------------------------------------------
# Helper Functions
# ------------------------------------------------------------------------------
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

# ------------------------------------------------------------------------------
# Currency Data Helpers
# ------------------------------------------------------------------------------
def download_currency_list():
    """Download the currency list CSV from the provided URL and return a list of dicts."""
    try:
        response = requests.get(CURRENCY_LIST_URL)
        if response.status_code == 200:
            df = pd.read_csv(io.StringIO(response.text))
            currencies = []
            for _, row in df.iterrows():
                code = str(row["currency code"]).strip()
                name = str(row["currency name"]).strip()
                currencies.append({
                    "ticker": code,
                    "symbol": code,
                    "name": name
                })
            return currencies
        else:
            logger.error("Failed to download currency list: " + response.text)
            return []
    except Exception as e:
        logger.error("Exception in downloading currency list: " + str(e))
        return []

def fetch_alpha_realtime_currency_rate(to_currency, from_currency="USD"):
    """Fetch realtime exchange rate using AlphaVantage's CURRENCY_EXCHANGE_RATE API."""
    url = "https://www.alphavantage.co/query"
    params = {
        "function": "CURRENCY_EXCHANGE_RATE",
        "from_currency": from_currency,
        "to_currency": to_currency,
        "apikey": ALPHAVANTAGE_API_KEY
    }
    try:
        response = requests.get(url, params=params, timeout=10)
        if response.status_code == 200:
            data = response.json()
            rate_info = data.get("Realtime Currency Exchange Rate", {})
            if rate_info:
                rate = rate_info.get("5. Exchange Rate")
                if rate:
                    return float(rate)
            logger.error(f"Error fetching realtime currency rate for {to_currency}: {response.text}")
        return "NOT_FOUND"
    except Exception as e:
        logger.error(f"Exception fetching realtime currency rate for {to_currency}: {e}")
        return "NOT_FOUND"

def fetch_alpha_fx_daily(from_symbol, to_symbol, start_date, end_date, outputsize="compact"):
    """Fetch historical FX daily data using AlphaVantage's FX_DAILY API and return a DataFrame."""
    url = "https://www.alphavantage.co/query"
    params = {
        "function": "FX_DAILY",
        "from_symbol": from_symbol,
        "to_symbol": to_symbol,
        "apikey": ALPHAVANTAGE_API_KEY,
        "outputsize": outputsize,
        "datatype": "json"
    }
    try:
        response = requests.get(url, params=params, timeout=10)
        if response.status_code == 200:
            data = response.json()
            time_series = data.get("Time Series FX (Daily)", {})
            if not time_series:
                return pd.DataFrame()
            records = []
            for date_str, day_data in time_series.items():
                date_obj = datetime.datetime.strptime(date_str, "%Y-%m-%d").date()
                if start_date and date_obj < datetime.datetime.strptime(start_date, "%Y-%m-%d").date():
                    continue
                if end_date and date_obj > datetime.datetime.strptime(end_date, "%Y-%m-%d").date():
                    continue
                records.append({
                    "date": date_obj,
                    "open": float(day_data["1. open"]),
                    "high": float(day_data["2. high"]),
                    "low": float(day_data["3. low"]),
                    "close": float(day_data["4. close"]),
                    "volume": None
                })
            if records:
                df = pd.DataFrame(records)
                df.sort_values("date", inplace=True)
                df.set_index("date", inplace=True)
                return df
        else:
            logger.error(f"Error fetching FX daily data for {to_symbol}: {response.text}")
    except Exception as e:
        logger.error(f"Exception fetching FX daily data for {to_symbol}: {e}")
    return pd.DataFrame()

def update_currency_database(currency_data, historical_data, upsert=False):
    """
    Update CurrencyAsset records and the corresponding AssetQuote and AssetPrice.
    For each currency (except USD), we create a quote from the currency asset to the USD asset.
    """
    session = Session()
    # Ensure USD asset exists (as CurrencyAsset)
    usd_asset = session.query(CurrencyAsset).filter_by(asset_type="CURRENCY", symbol="USD").first()
    if not usd_asset:
        base_usd = Asset(asset_type="CURRENCY", symbol="USD", name="United States Dollar", discriminator="CURRENCY")
        usd_asset = CurrencyAsset(asset_type="CURRENCY", symbol="USD")
        session.merge(base_usd)
        session.merge(usd_asset)
        session.commit()

    for item in currency_data:
        ticker = item["ticker"]
        base_asset = Asset(asset_type="CURRENCY", symbol=ticker, name=item["name"], discriminator="CURRENCY")
        currency_asset = CurrencyAsset(asset_type="CURRENCY", symbol=ticker)
        session.merge(base_asset)
        session.merge(currency_asset)
    session.commit()

    for item in currency_data:
        ticker = item["ticker"]
        if ticker.upper() == "USD":
            continue
        quote_ticker = ticker.upper() + "USD"
        existing_quote = session.query(AssetQuote).filter_by(ticker=quote_ticker).first()
        if not existing_quote:
            new_quote = AssetQuote(
                ticker=quote_ticker,
                from_asset_type="CURRENCY",
                from_asset_symbol=ticker.upper(),
                to_asset_type="CURRENCY",
                to_asset_symbol="USD"
            )
            session.add(new_quote)
    session.commit()

    for ticker, df in historical_data.items():
        if df is None or df.empty:
            continue
        quote_ticker = ticker.upper() + "USD"
        for date, data_row in df.iterrows():
            price_datetime = datetime.datetime.combine(date, datetime.datetime.min.time())
            mapping = {
                "ticker": quote_ticker,
                "price_datetime": price_datetime,
                "data_source_id": 1,
                "open_price": safe_convert(data_row.get("open"), float),
                "high_price": safe_convert(data_row.get("high"), float),
                "low_price": safe_convert(data_row.get("low"), float),
                "close_price": safe_convert(data_row.get("close"), float),
                "volume": None
            }
            if upsert:
                session.merge(AssetPrice(**mapping))
                session.commit()
            else:
                session.add(AssetPrice(**mapping))
        session.commit()
    session.close()

def full_sync_currency():
    logger.info("Starting Full Sync for Currencies...")
    currency_list = download_currency_list()
    historical_data = {}
    for currency in currency_list:
        ticker = currency["ticker"]
        if ticker.upper() == "USD":
            continue
        df = fetch_alpha_fx_daily(ticker.upper(), "USD", HISTORICAL_START_DATE, None, outputsize="full")
        historical_data[ticker] = df
        time.sleep(REQUEST_DELAY_SECONDS)
    update_currency_database(currency_list, historical_data, upsert=False)
    session = Session()
    state = session.query(DeltaSyncState).filter_by(id=2).first()
    if not state:
        state = DeltaSyncState(id=2)
    state.last_full_sync = datetime.datetime.now()
    session.merge(state)
    session.commit()
    session.close()
    logger.info("Full Sync for Currencies Completed.")

def delta_sync_currency():
    logger.info("Starting Delta Sync for Currencies...")
    session = Session()
    state = session.query(DeltaSyncState).filter_by(id=2).first()
    session.close()
    today = datetime.datetime.now().date()
    two_days_ago = today - datetime.timedelta(days=2)
    currency_list = download_currency_list()
    historical_data = {}
    for currency in currency_list:
        ticker = currency["ticker"]
        if ticker.upper() == "USD":
            continue
        df = fetch_alpha_fx_daily(ticker.upper(), "USD", two_days_ago.strftime("%Y-%m-%d"), today.strftime("%Y-%m-%d"), outputsize="compact")
        historical_data[ticker] = df
        time.sleep(REQUEST_DELAY_SECONDS)
    update_currency_database(currency_list, historical_data, upsert=True)
    session = Session()
    state = session.query(DeltaSyncState).filter_by(id=2).first()
    if not state:
        state = DeltaSyncState(id=2)
    state.last_delta_sync = datetime.datetime.now()
    session.merge(state)
    session.commit()
    session.close()
    logger.info("Delta Sync for Currencies Completed.")

# ------------------------------------------------------------------------------
# Stock & Crypto Functions (Updated for New Model)
# ------------------------------------------------------------------------------
def fetch_yf_data_for_ticker(ticker, start_date=HISTORICAL_START_DATE, end_date=None):
    logger.info(f"Fetching data for stock ticker: {ticker}")
    try:
        import yfinance as yf
        data = yf.Ticker(ticker)
        hist = data.history(start=start_date, end=end_date)
        if hist.empty:
            return None, None
        quotes_df = pd.DataFrame([{
            "symbol": ticker,
            "name": data.info.get("longName") or data.info.get("displayName") or ticker,
            "language": data.info.get("language"),
            "region": data.info.get("region"),
            "quote_type": data.info.get("quoteType"),
            "exchange": data.info.get("exchange"),
            "full_exchange_name": data.info.get("fullExchangeName"),
            "first_trade_date": data.info.get("firstTradeDateEpochUtc")
        }])
        historical_data = {ticker: hist}
        return quotes_df, historical_data
    except Exception as e:
        logger.error(f"Error fetching data for {ticker}: {e}")
        return None, None

def fetch_yf_data(max_tickers_per_request, delay_t, query, start_date=HISTORICAL_START_DATE, end_date=None, sample_size=None):
    logger.info("Starting data fetch from yfinance for stocks...")
    import yfinance as yf
    all_quotes = []
    offset = 0
    size = sample_size if sample_size is not None else 250
    if sample_size is not None:
        result = yf.screen(query, offset=0, size=sample_size)
        quotes = result.get("quotes", [])
        all_quotes.extend(quotes)
    else:
        while True:
            result = yf.screen(query, offset=offset, size=size)
            quotes = result.get("quotes", [])
            if not quotes:
                break
            all_quotes.extend(quotes)
            offset += size
    quotes_df = pd.DataFrame(all_quotes)
    symbols = [quote.get("symbol") for quote in all_quotes if quote.get("symbol")]
    historical_data = {}
    for batch_symbols in chunk_list(symbols, max_tickers_per_request):
        tickers_str = " ".join(batch_symbols)
        data = yf.download(tickers=tickers_str, start=start_date, end=end_date, interval="1d", group_by='ticker')
        if isinstance(data.columns, pd.MultiIndex):
            available_tickers = data.columns.get_level_values(0).unique().tolist()
            for ticker in batch_symbols:
                if ticker in available_tickers:
                    historical_data[ticker] = data[ticker]
        else:
            ticker = batch_symbols[0]
            historical_data[ticker] = data
        time.sleep(delay_t)
    return quotes_df, historical_data

def update_stock_database(quotes_df, historical_data, upsert=False):
    session = Session()
    exchange_to_currency = {"NMS": "USD", "NYQ": "USD", "SET": "THB"}
    for cur in set(exchange_to_currency.values()):
        currency_asset = session.query(CurrencyAsset).filter_by(asset_type="CURRENCY", symbol=cur).first()
        if not currency_asset:
            base_cur = Asset(asset_type="CURRENCY", symbol=cur, name=("United States Dollar" if cur=="USD" else cur), discriminator="CURRENCY")
            currency_asset = CurrencyAsset(asset_type="CURRENCY", symbol=cur)
            session.merge(base_cur)
            session.merge(currency_asset)
    session.commit()

    for idx, row in quotes_df.iterrows():
        ticker = row.get("symbol")
        if not ticker:
            continue
        base_asset = Asset(asset_type="STOCK", symbol=ticker, name=row.get("name") or ticker, discriminator="STOCK")
        stock_asset = StockAsset(
            asset_type="STOCK",
            symbol=ticker,
            exchange=row.get("exchange"),
            region=row.get("region"),
            language=row.get("language"),
            quote_type=row.get("quote_type"),
            full_exchange_name=row.get("full_exchange_name"),
            first_trade_date=safe_convert(row.get("first_trade_date"), lambda x: datetime.datetime.fromtimestamp(x).date())
        )
        session.merge(base_asset)
        session.merge(stock_asset)

        exchange = row.get("exchange")
        quote_cur = exchange_to_currency.get(exchange, "USD")
        currency_asset = session.query(CurrencyAsset).filter_by(asset_type="CURRENCY", symbol=quote_cur).first()
        quote_ticker = ticker + quote_cur
        existing_quote = session.query(AssetQuote).filter_by(ticker=quote_ticker).first()
        if not existing_quote:
            new_quote = AssetQuote(
                ticker=quote_ticker,
                from_asset_type="STOCK",
                from_asset_symbol=ticker,
                to_asset_type="CURRENCY",
                to_asset_symbol=quote_cur
            )
            session.add(new_quote)
        session.commit()

    for ticker, df in historical_data.items():
        cur_row = quotes_df[quotes_df["symbol"] == ticker]
        if not cur_row.empty:
            exchange = cur_row.iloc[0].get("exchange")
            quote_cur = exchange_to_currency.get(exchange, "USD")
            quote_ticker = ticker + quote_cur
        else:
            quote_ticker = ticker + "USD"
        for date, data_row in df.iterrows():
            price_datetime = datetime.datetime.combine(date, datetime.datetime.min.time())
            mapping = {
                "ticker": quote_ticker,
                "price_datetime": price_datetime,
                "data_source_id": 1,
                "open_price": safe_convert(data_row.get("Open"), float),
                "high_price": safe_convert(data_row.get("High"), float),
                "low_price": safe_convert(data_row.get("Low"), float),
                "close_price": safe_convert(data_row.get("Close"), float),
                "volume": safe_convert(data_row.get("Volume"), Decimal)
            }
            if upsert:
                session.merge(AssetPrice(**mapping))
                session.commit()
            else:
                session.add(AssetPrice(**mapping))
        session.commit()
    session.close()

def update_crypto_database(crypto_data, historical_data, upsert=False):
    session = Session()
    usdt_asset = session.query(CurrencyAsset).filter_by(asset_type="CURRENCY", symbol="USDT").first()
    if not usdt_asset:
        base_usdt = Asset(asset_type="CURRENCY", symbol="USDT", name="Tether", discriminator="CURRENCY")
        usdt_asset = CurrencyAsset(asset_type="CURRENCY", symbol="USDT")
        session.merge(base_usdt)
        session.merge(usdt_asset)
        session.commit()

    for coin in crypto_data:
        coin_id = coin.get("id")
        symbol = coin.get("symbol").upper()
        base_crypto = Asset(asset_type="CRYPTO", symbol=symbol, name=coin.get("name"), discriminator="CRYPTO")
        crypto_asset = CryptoAsset(
            asset_type="CRYPTO",
            symbol=symbol,
            image=coin.get("image"),
            ath=coin.get("ath"),
            ath_date=coin.get("ath_date"),
            atl=coin.get("atl"),
            atl_date=coin.get("atl_date"),
            total_supply=coin.get("total_supply"),
            max_supply=coin.get("max_supply")
        )
        session.merge(base_crypto)
        session.merge(crypto_asset)
        quote_ticker = symbol + "USDT"
        existing_quote = session.query(AssetQuote).filter_by(ticker=quote_ticker).first()
        if not existing_quote:
            new_quote = AssetQuote(
                ticker=quote_ticker,
                from_asset_type="CRYPTO",
                from_asset_symbol=symbol,
                to_asset_type="CURRENCY",
                to_asset_symbol="USDT"
            )
            session.add(new_quote)
        session.commit()

    for coin in crypto_data:
        symbol = coin.get("symbol").upper()
        quote_ticker = symbol + "USDT"
        df = historical_data.get(coin.get("id"))
        if df is None or df.empty:
            continue
        for date, data_row in df.iterrows():
            price_datetime = datetime.datetime.combine(date, datetime.datetime.min.time())
            mapping = {
                "ticker": quote_ticker,
                "price_datetime": price_datetime,
                "data_source_id": 2,
                "open_price": safe_convert(data_row.get("open"), float),
                "high_price": safe_convert(data_row.get("high"), float),
                "low_price": safe_convert(data_row.get("low"), float),
                "close_price": safe_convert(data_row.get("close"), float),
                "volume": None
            }
            if upsert:
                session.merge(AssetPrice(**mapping))
                session.commit()
            else:
                session.add(AssetPrice(**mapping))
        session.commit()
    session.close()

def full_sync_stocks():
    logger.info("Starting Full Sync for Stocks...")
    import yfinance as yf
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
    import yfinance as yf
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

def full_sync_crypto():
    logger.info("Starting Full Sync for Cryptocurrencies...")
    crypto_data = fetch_coingecko_data()  # Assume this function exists and returns a list of crypto metadata
    historical_data = {}
    for coin in crypto_data:
        coin_id = coin.get("id")
        coin_symbol = coin.get("symbol").upper()
        df = fetch_binance_crypto_data(coin_symbol + "USDT", HISTORICAL_START_DATE, None)  # Assume this function exists
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
    crypto_data = fetch_coingecko_data()  # Assume this function exists
    historical_data = {}
    for coin in crypto_data:
        coin_id = coin.get("id")
        coin_symbol = coin.get("symbol").upper()
        df = fetch_binance_crypto_data(coin_symbol + "USDT", two_days_ago.strftime("%Y-%m-%d"), today.strftime("%Y-%m-%d"))
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

# ------------------------------------------------------------------------------
# DataSource Classes for Latest Price Fetching
# ------------------------------------------------------------------------------
class StockDataSource:
    @staticmethod
    def get_latest_price(ticker):
        try:
            import yfinance as yf
            data = yf.Ticker(ticker)
            return data.fast_info["last_price"]
        except KeyError:
            return "NOT_FOUND"
        except Exception as e:
            logger.error(f"Error fetching latest price for stock {ticker}: {e}")
            return None

    @staticmethod
    def refresh_latest_prices(tickers):
        prices = {}
        tickers_str = " ".join(tickers)
        import yfinance as yf
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
        response = requests.get(url, params=params, headers=headers)
        if response.status_code == 200:
            data = response.json()
            return {coin["id"]: coin["current_price"] for coin in data}
        return {}

    @staticmethod
    def get_latest_price(ticker):
        prices = CryptoDataSource.get_all_latest_prices()
        return prices.get(ticker, "NOT_FOUND")

class CurrencyDataSource:
    @staticmethod
    def get_latest_price(ticker):
        from_currency = ticker[:-3]
        return fetch_alpha_realtime_currency_rate("USD", from_currency=from_currency)

    @staticmethod
    def get_all_latest_prices():
        currency_list = download_currency_list()
        prices = {}
        for currency in currency_list:
            ticker = currency["ticker"]
            if ticker.upper() == "USD":
                prices[ticker] = 1.0
            else:
                price = fetch_alpha_realtime_currency_rate("USD", from_currency=ticker)
                prices[ticker] = price
            time.sleep(REQUEST_DELAY_SECONDS)
        return prices

# ------------------------------------------------------------------------------
# Unified Latest Price and Cache Refresh
# ------------------------------------------------------------------------------
def get_latest_price(ticker, asset_type="STOCK"):
    key = (ticker,)
    query_counter[key] += 1
    now = datetime.datetime.now()
    if key in latest_cache:
        value, timestamp = latest_cache[key]
        if value == "NOT_FOUND" and (now - timestamp).total_seconds() / 60 < NOT_FOUND_TTL:
            return "NOT_FOUND"
        elif value is not None and (now - timestamp).total_seconds() / 60 < REGULAR_TTL:
            return value
    if asset_type.upper() == "STOCK":
        price = StockDataSource.get_latest_price(ticker)
    elif asset_type.upper() == "CRYPTO":
        price = CryptoDataSource.get_latest_price(ticker)
    elif asset_type.upper() == "CURRENCY":
        price = CurrencyDataSource.get_latest_price(ticker)
    else:
        price = None
    if price == "NOT_FOUND":
        latest_cache[key] = ("NOT_FOUND", now)
        return "NOT_FOUND"
    elif price is not None:
        latest_cache[key] = (price, now)
        return price
    return "FETCH_ERROR"

def refresh_stock_top_n_tickers():
    top_tickers = [ticker for (ticker,), _ in query_counter.most_common(TOP_N_TICKERS)]
    for batch in chunk_list(top_tickers, MAX_TICKERS_PER_REQUEST):
        prices = StockDataSource.refresh_latest_prices(batch)
        now = datetime.datetime.now()
        for ticker, price in prices.items():
            latest_cache[(ticker,)] = (price, now)
        time.sleep(REQUEST_DELAY_SECONDS)

def refresh_crypto_prices():
    prices = CryptoDataSource.get_all_latest_prices()
    now = datetime.datetime.now()
    for ticker, price in prices.items():
        latest_cache[(ticker,)] = (price, now)

def refresh_currency_prices():
    prices = CurrencyDataSource.get_all_latest_prices()
    now = datetime.datetime.now()
    for ticker, price in prices.items():
        quote_ticker = ticker.upper() + "USD"
        latest_cache[(quote_ticker,)] = (price, now)

def refresh_all_latest_prices():
    refresh_stock_top_n_tickers()
    refresh_crypto_prices()
    refresh_currency_prices()
    global last_cache_refresh
    last_cache_refresh = datetime.datetime.now()

def load_query_counter():
    session = Session()
    query_counts = session.query(QueryCount).all()
    for qc in query_counts:
        key = (qc.ticker,)
        query_counter[key] = qc.count
        last_saved_counts[key] = qc.count
    session.close()

def save_query_counter():
    session = Session()
    for (ticker,), current_count in query_counter.items():
        key = (ticker,)
        baseline = last_saved_counts.get(key, 0)
        delta = current_count - baseline
        if delta > 0:
            existing = session.query(QueryCount).filter_by(ticker=ticker, asset_type="").first()
            if existing:
                existing.count += delta
            else:
                session.add(QueryCount(ticker=ticker, asset_type="", count=current_count))
            last_saved_counts[key] = current_count
    session.commit()
    session.close()

# ------------------------------------------------------------------------------
# Flask Application and Endpoints
# ------------------------------------------------------------------------------
app = Flask(__name__)
api_stats = Counter()

@app.route("/api/unified")
def get_unified_ticker():
    ticker = request.args.get("ticker")
    asset_type = request.args.get("asset_type", "STOCK").upper()
    if not ticker:
        return jsonify({"error": "Ticker parameter is required"}), 400
    session = Session()
    quote = session.query(AssetQuote).join(Asset, 
                (Asset.asset_type == AssetQuote.from_asset_type) & (Asset.symbol == AssetQuote.from_asset_symbol)
            ).filter(AssetQuote.ticker == ticker, Asset.asset_type == asset_type).first()
    if not quote:
        session.close()
        return jsonify({"error": "Ticker not found"}), 404
    quote_data = {
        "ticker": quote.ticker,
        "from_asset": {
            "asset_type": quote.from_asset.asset_type,
            "symbol": quote.from_asset.symbol,
            "name": quote.from_asset.name,
        },
        "to_asset": {
            "asset_type": quote.to_asset.asset_type,
            "symbol": quote.to_asset.symbol,
            "name": quote.to_asset.name,
        }
    }
    prices = session.query(AssetPrice).filter_by(ticker=ticker).all()
    session.close()
    cache_entry = latest_cache.get((ticker,), (None, None))
    latest_cache_data = {
        "price": cache_entry[0],
        "timestamp": cache_entry[1].isoformat() if cache_entry[1] else None
    }
    historical = [{
        "price_datetime": price.price_datetime.isoformat(),
        "open": float(price.open_price) if price.open_price is not None else None,
        "high": float(price.high_price) if price.high_price is not None else None,
        "low": float(price.low_price) if price.low_price is not None else None,
        "close": float(price.close_price) if price.close_price is not None else None,
        "volume": float(price.volume) if price.volume is not None else None,
        "data_source_id": price.data_source_id
    } for price in prices]
    unified_data = {
        "ticker": ticker,
        "quote_data": quote_data,
        "latest_cache": latest_cache_data,
        "historical_data": historical
    }
    return jsonify(unified_data)

@app.route("/api/data_quality")
def data_quality():
    session = Session()
    total_stock_assets = session.query(StockAsset).count()
    total_crypto_assets = session.query(CryptoAsset).count()
    total_currency_assets = session.query(CurrencyAsset).count()
    missing_names = session.query(Asset).filter(Asset.name.is_(None)).count()
    duplicate_entries = session.query(AssetPrice.ticker, func.count(AssetPrice.ticker).label("dup_count")
                                      ).group_by(AssetPrice.ticker).having(func.count(AssetPrice.ticker) > 1).all()
    dup_total = sum(dup.dup_count - 1 for dup in duplicate_entries)
    session.close()
    data_quality_metrics = {
        "total_stock_assets": total_stock_assets,
        "total_crypto_assets": total_crypto_assets,
        "total_currency_assets": total_currency_assets,
        "missing_names": missing_names,
        "duplicate_price_entries": dup_total
    }
    return jsonify(data_quality_metrics)

@app.route("/api/ticker_traffic")
def ticker_traffic():
    data = [{"ticker": t[0], "count": count} for t, count in query_counter.most_common()]
    return jsonify(data)

@app.route("/api/cache_info")
def cache_info():
    global last_cache_refresh
    scheduler_job = scheduler.get_job("cache_refresh")
    if scheduler_job and scheduler_job.next_run_time:
        now_aware = datetime.datetime.now(tz=scheduler_job.next_run_time.tzinfo)
        diff_seconds = (scheduler_job.next_run_time - now_aware).total_seconds()
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
        key = request.path + request.args.get("ticker", "") + request.args.get("asset_type", "STOCK").upper()
        api_stats[key] += 1

@app.route("/api/latest")
def get_latest():
    ticker = request.args.get("ticker")
    asset_type = request.args.get("asset_type", "STOCK").upper()
    if not ticker:
        return jsonify({"error": "Ticker parameter is required"}), 400
    result = get_latest_price(ticker, asset_type)
    key = (ticker,)
    timestamp = latest_cache.get(key, (None, datetime.datetime.now()))[1]
    if isinstance(result, (int, float)):
        return jsonify({
            "ticker": ticker,
            "price": result,
            "timestamp": timestamp.isoformat() if timestamp else None
        })
    elif result == "NOT_FOUND":
        return jsonify({"error": "Ticker not found"}), 404
    else:
        return jsonify({"error": "Unable to fetch latest price"}), 500

@app.route("/api/assets")
def get_assets():
    session = Session()
    assets = session.query(Asset).all()
    session.close()
    assets_list = [{
        "asset_type": asset.asset_type,
        "symbol": asset.symbol,
        "name": asset.name
    } for asset in assets]
    return jsonify(assets_list)

@app.route("/api/historical")
def get_historical():
    ticker = request.args.get("ticker")
    if not ticker:
        return jsonify({"error": "Ticker parameter is required"}), 400
    session = Session()
    prices = session.query(AssetPrice).filter_by(ticker=ticker).all()
    session.close()
    if not prices:
        return jsonify({"error": "No historical data found for ticker"}), 404
    data = []
    for price in prices:
        record = {
            "price_datetime": price.price_datetime.isoformat(),
            "open": float(price.open_price) if price.open_price is not None else None,
            "high": float(price.high_price) if price.high_price is not None else None,
            "low": float(price.low_price) if price.low_price is not None else None,
            "close": float(price.close_price) if price.close_price is not None else None,
            "volume": float(price.volume) if price.volume is not None else None,
            "data_source_id": price.data_source_id
        }
        data.append(record)
    return jsonify({"ticker": ticker, "historical_data": data})

@app.route("/api/stats")
def get_stats():
    session = Session()
    total_stock_assets = session.query(StockAsset).count()
    total_crypto_assets = session.query(CryptoAsset).count()
    total_currency_assets = session.query(CurrencyAsset).count()
    price_counts = session.query(AssetPrice).count()
    delta_sync_state_count = session.query(DeltaSyncState).count()
    query_counts_count = session.query(QueryCount).count()
    session.close()
    db_file = os.path.join('instance', 'stock_data.db')
    if os.path.exists(db_file):
        db_size = os.path.getsize(db_file) / (1024 * 1024)
        db_size_str = f"{db_size:.2f} MB" if db_size < 1024 else f"{db_size / 1024:.2f} GB"
    else:
        db_size_str = "Database file not found"
    stats = {
        "total_stock_assets": total_stock_assets,
        "total_crypto_assets": total_crypto_assets,
        "total_currency_assets": total_currency_assets,
        "price_records": price_counts,
        "delta_sync_state": delta_sync_state_count,
        "query_counts": query_counts_count,
        "db_size": db_size_str,
        "cache_size": len(latest_cache),
        "api_requests_24h": sum(api_stats.values()),
        "api_stats": dict(api_stats)
    }
    return jsonify(stats)

@app.route("/api/tickers")
def get_tickers():
    query = request.args.get("query", "").strip().lower()
    if not query:
        return jsonify({"error": "Query parameter is required"}), 400
    asset_type = request.args.get("asset_type", "STOCK").upper()
    try:
        limit = int(request.args.get("limit", 10))
        page = int(request.args.get("page", 1))
        limit = min(limit, MAX_TICKERS_PER_REQUEST)
        offset = (page - 1) * limit
    except ValueError:
        return jsonify({"error": "Invalid pagination parameters"}), 400
    fuzzy_enabled = request.args.get("fuzzy", "false").lower() == "true"
    try:
        session = Session()
        base_query = session.query(AssetQuote).join(Asset, (Asset.asset_type == AssetQuote.from_asset_type) & (Asset.symbol == AssetQuote.from_asset_symbol))\
            .filter(
                (AssetQuote.ticker.ilike(f"%{query}%")) |
                (Asset.name.ilike(f"%{query}%"))
            )
        if fuzzy_enabled:
            candidate_results = base_query.limit(50).all()
            scored_results = []
            for record in candidate_results:
                score = max(
                    fuzz.token_set_ratio(query, record.ticker.lower()),
                    fuzz.token_set_ratio(query, record.from_asset.name.lower() if record.from_asset.name else ""),
                    fuzz.token_set_ratio(query, record.from_asset.symbol.lower())
                )
                scored_results.append((score, record))
            scored_results.sort(key=lambda x: x[0], reverse=True)
            final_results = [record for _, record in scored_results[offset: offset + limit]]
        else:
            final_results = base_query.offset(offset).limit(limit).all()
        session.close()
        response = [{
            "ticker": r.ticker,
            "from_asset": {
                "symbol": r.from_asset.symbol,
                "name": r.from_asset.name
            },
            "to_asset": {
                "symbol": r.to_asset.symbol,
                "name": r.to_asset.name
            }
        } for r in final_results]
        return jsonify(response)
    except SQLAlchemyError as e:
        current_app.logger.error(f"Database error in get_tickers: {e}")
        return jsonify({"error": "Internal server error"}), 500
    except Exception as e:
        current_app.logger.error(f"Unexpected error in get_tickers: {e}")
        return jsonify({"error": "Internal server error"}), 500

@app.route("/api/sync/full", methods=["POST"])
def sync_full():
    data = request.get_json() or {}
    ticker = data.get("ticker")
    asset_type = data.get("asset_type", "STOCK").upper()
    try:
        if ticker:
            if asset_type == "STOCK":
                quotes_df, historical_data = fetch_yf_data_for_ticker(ticker)
                if quotes_df is not None and historical_data is not None:
                    update_stock_database(quotes_df, historical_data, upsert=True)
                    return jsonify({"message": f"Full sync for stock ticker {ticker} completed."})
                else:
                    return jsonify({"error": f"Failed to fetch data for stock ticker {ticker}"}), 404
            elif asset_type == "CRYPTO":
                coin_data = fetch_coingecko_data_for_ticker(ticker)  # Assume this exists
                if coin_data:
                    symbol = coin_data["symbol"].upper()
                    historical_data = fetch_binance_crypto_data(symbol + "USDT", HISTORICAL_START_DATE, None)
                    if historical_data is not None:
                        update_crypto_database([coin_data], {ticker: historical_data}, upsert=True)
                        return jsonify({"message": f"Full sync for crypto ticker {ticker} completed."})
                    else:
                        return jsonify({"error": f"Failed to fetch historical data for crypto ticker {ticker}"}), 404
                else:
                    return jsonify({"error": f"Failed to fetch metadata for crypto ticker {ticker}"}), 404
            elif asset_type == "CURRENCY":
                currency_item = None
                currency_list = download_currency_list()
                for item in currency_list:
                    if item["ticker"].lower() == ticker.lower():
                        currency_item = item
                        break
                if currency_item:
                    df = fetch_alpha_fx_daily(currency_item["ticker"].upper(), "USD", HISTORICAL_START_DATE, None, outputsize="full")
                    update_currency_database([currency_item], {currency_item["ticker"]: df}, upsert=True)
                    return jsonify({"message": f"Full sync for currency ticker {ticker} completed."})
                else:
                    return jsonify({"error": f"Failed to fetch data for currency ticker {ticker}"}), 404
            else:
                return jsonify({"error": "Invalid asset_type"}), 400
        else:
            if asset_type == "CRYPTO":
                full_sync_crypto()
                return jsonify({"message": "Global full sync for cryptocurrencies completed."})
            elif asset_type == "CURRENCY":
                full_sync_currency()
                return jsonify({"message": "Global full sync for currencies completed."})
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
            today = datetime.datetime.now().date()
            two_days_ago = today - datetime.timedelta(days=2)
            if asset_type == "STOCK":
                quotes_df, historical_data = fetch_yf_data_for_ticker(ticker, start_date=two_days_ago.strftime("%Y-%m-%d"), end_date=today.strftime("%Y-%m-%d"))
                if quotes_df is not None and historical_data is not None:
                    update_stock_database(quotes_df, historical_data, upsert=True)
                    return jsonify({"message": f"Delta sync for stock ticker {ticker} completed."})
                else:
                    return jsonify({"error": f"Failed to fetch delta data for stock ticker {ticker}"}), 404
            elif asset_type == "CRYPTO":
                coin_data = fetch_coingecko_data_for_ticker(ticker)
                if coin_data:
                    symbol = coin_data["symbol"].upper()
                    historical_data = fetch_binance_crypto_data(symbol + "USDT", two_days_ago.strftime("%Y-%m-%d"), today.strftime("%Y-%m-%d"))
                    if historical_data is not None:
                        update_crypto_database([coin_data], {ticker: historical_data}, upsert=True)
                        return jsonify({"message": f"Delta sync for crypto ticker {ticker} completed."})
                    else:
                        return jsonify({"error": f"Failed to fetch delta historical data for crypto ticker {ticker}"}), 404
                else:
                    return jsonify({"error": f"Failed to fetch metadata for crypto ticker {ticker}"}), 404
            elif asset_type == "CURRENCY":
                currency_item = None
                currency_list = download_currency_list()
                for item in currency_list:
                    if item["ticker"].lower() == ticker.lower():
                        currency_item = item
                        break
                if currency_item:
                    df = fetch_alpha_fx_daily(currency_item["ticker"].upper(), "USD", two_days_ago.strftime("%Y-%m-%d"), today.strftime("%Y-%m-%d"), outputsize="compact")
                    update_currency_database([currency_item], {currency_item["ticker"]: df}, upsert=True)
                    return jsonify({"message": f"Delta sync for currency ticker {ticker} completed."})
                else:
                    return jsonify({"error": f"Failed to fetch data for currency ticker {ticker}"}), 404
            else:
                return jsonify({"error": "Invalid asset_type"}), 400
        else:
            if asset_type == "CRYPTO":
                delta_sync_crypto()
                return jsonify({"message": "Global delta sync for cryptocurrencies completed."})
            elif asset_type == "CURRENCY":
                delta_sync_currency()
                return jsonify({"message": "Global delta sync for currencies completed."})
            else:
                delta_sync_stocks()
                return jsonify({"message": "Global delta sync for stocks completed."})
    except Exception as e:
        logger.error(f"Error in delta sync: {e}")
        return jsonify({"error": str(e)}), 500

@app.route("/dashboard")
def dashboard():
    return render_template('dashboard.html')

# ------------------------------------------------------------------------------
# Scheduler Setup
# ------------------------------------------------------------------------------
scheduler = BackgroundScheduler()
scheduler.add_job(refresh_all_latest_prices, "interval", minutes=LATEST_CACHE_REFRESH_INTERVAL_MINUTES, id="cache_refresh")
scheduler.add_job(delta_sync_stocks, "interval", days=DELTA_SYNC_INTERVAL_DAYS, id="delta_sync_stocks")
scheduler.add_job(delta_sync_crypto, "interval", days=DELTA_SYNC_INTERVAL_DAYS, id="delta_sync_crypto")
scheduler.add_job(delta_sync_currency, "interval", days=DELTA_SYNC_INTERVAL_DAYS, id="delta_sync_currency")
scheduler.add_job(save_query_counter, "interval", minutes=QUERY_COUNTER_SAVE_INTERVAL_MINUTES, id="save_query_counter")
scheduler.add_job(refresh_currency_prices, "interval", minutes=60, id="currency_cache_refresh")
scheduler.start()
load_query_counter()

if __name__ == "__main__":
    session = Session()
    stock_count = session.query(StockAsset).count()
    crypto_count = session.query(CryptoAsset).count()
    currency_count = session.query(CurrencyAsset).count()
    session.close()
    if stock_count == 0 or crypto_count == 0 or currency_count == 0:
        Base.metadata.drop_all(engine)
        Base.metadata.create_all(engine)
        refresh_all_latest_prices()
    app.run(host=FLASK_HOST, port=FLASK_PORT)
