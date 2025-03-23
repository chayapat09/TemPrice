import datetime
import time
import logging
import os
from collections import Counter
from flask import Flask, jsonify, request, render_template, current_app
from sqlalchemy import BigInteger, Column, Date, DateTime, DECIMAL, Integer, String, ForeignKey, create_engine, func, text, and_, ForeignKeyConstraint
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker, relationship
from apscheduler.schedulers.background import BackgroundScheduler
import pandas as pd
import yfinance as yf
import requests
from decimal import Decimal
from rapidfuzz import fuzz  # for fuzzy matching
from sqlalchemy.exc import SQLAlchemyError

# Ensure the 'instance' directory exists
if not os.path.exists('instance'):
    os.makedirs('instance')

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
TOP_N_TICKERS = 100
LATEST_CACHE_REFRESH_INTERVAL_MINUTES = 1
REGULAR_TTL = 15
NOT_FOUND_TTL = 1440
QUERY_COUNTER_SAVE_INTERVAL_MINUTES = 5
DELTA_SYNC_INTERVAL_DAYS = 1

# Global variable to track last cache refresh
last_cache_refresh = None

# SQLAlchemy Setup and Models
Base = declarative_base()

# ---------- Asset Models ----------
# Added new field: source_asset_key to store the key to use for price queries.

class Asset(Base):
    __tablename__ = "assets"
    asset_type = Column(String(10), primary_key=True)  # e.g. STOCK, CRYPTO, CURRENCY
    symbol = Column(String(50), primary_key=True)
    name = Column(String(100))
    source_asset_key = Column(String(50))  # For stocks: same as symbol; for crypto: coin_id from CoinGecko
    __mapper_args__ = {
        'polymorphic_on': asset_type,
        'polymorphic_identity': 'ASSET'
    }

class StockAsset(Asset):
    __tablename__ = "stock_assets"
    asset_type = Column(String(10), primary_key=True)
    symbol = Column(String(50), primary_key=True)
    language = Column(String(10))
    region = Column(String(10))
    exchange = Column(String(50))
    full_exchange_name = Column(String(100))
    first_trade_date = Column(Date)
    __table_args__ = (
        ForeignKeyConstraint([asset_type, symbol], ["assets.asset_type", "assets.symbol"]),
    )
    __mapper_args__ = {
        'polymorphic_identity': 'STOCK',
        'inherit_condition': and_(asset_type == Asset.asset_type, symbol == Asset.symbol)
    }

class CryptoAsset(Asset):
    __tablename__ = "crypto_assets"
    asset_type = Column(String(10), primary_key=True)
    symbol = Column(String(50), primary_key=True)
    image = Column(String(200))
    ath = Column(DECIMAL(15, 2))
    ath_date = Column(DateTime)
    atl = Column(DECIMAL(15, 2))
    atl_date = Column(DateTime)
    total_supply = Column(BigInteger)
    max_supply = Column(BigInteger)
    __table_args__ = (
        ForeignKeyConstraint([asset_type, symbol], ["assets.asset_type", "assets.symbol"]),
    )
    __mapper_args__ = {
        'polymorphic_identity': 'CRYPTO',
        'inherit_condition': and_(asset_type == Asset.asset_type, symbol == Asset.symbol)
    }

class CurrencyAsset(Asset):
    __tablename__ = "currency_assets"
    asset_type = Column(String(10), primary_key=True)
    symbol = Column(String(50), primary_key=True)
    # Additional fields specific to currency can be added here
    __table_args__ = (
        ForeignKeyConstraint([asset_type, symbol], ["assets.asset_type", "assets.symbol"]),
    )
    __mapper_args__ = {
        'polymorphic_identity': 'CURRENCY',
        'inherit_condition': and_(asset_type == Asset.asset_type, symbol == Asset.symbol)
    }

# ---------- Data Source Model ----------

class DataSource(Base):
    __tablename__ = "data_sources"
    id = Column(Integer, primary_key=True)
    name = Column(String(50), unique=True)
    description = Column(String(200), nullable=True)

# ---------- Asset Price / Quote Models ----------

class AssetQuote(Base):
    __tablename__ = "asset_quotes"
    id = Column(Integer, primary_key=True)
    from_asset_type = Column(String(10))
    from_asset_symbol = Column(String(50))
    to_asset_type = Column(String(10))
    to_asset_symbol = Column(String(50))
    data_source_id = Column(Integer, ForeignKey("data_sources.id"))
    ticker = Column(String(50))          # Composite ticker: e.g. for stocks "TSLAUSD", for crypto "BTCUSDT"
    source_ticker = Column(String(50))   # The key used to query the price datasource (for stocks: TSLA; for crypto: BTCUSDT)

    __table_args__ = (
        ForeignKeyConstraint([from_asset_type, from_asset_symbol], ["assets.asset_type", "assets.symbol"]),
        ForeignKeyConstraint([to_asset_type, to_asset_symbol], ["assets.asset_type", "assets.symbol"]),
    )

    from_asset = relationship("Asset", foreign_keys=[from_asset_type, from_asset_symbol])
    to_asset = relationship("Asset", foreign_keys=[to_asset_type, to_asset_symbol])
    data_source = relationship("DataSource")

class AssetOHLCV(Base):
    __tablename__ = "asset_ohlcv"
    id = Column(Integer, primary_key=True)
    asset_quote_id = Column(Integer, ForeignKey("asset_quotes.id"))
    price_date = Column(DateTime)
    open_price = Column(DECIMAL(10, 2))
    high_price = Column(DECIMAL(10, 2))
    low_price = Column(DECIMAL(10, 2))
    close_price = Column(DECIMAL(10, 2))
    volume = Column(DECIMAL(20, 8))

    asset_quote = relationship("AssetQuote")

# ---------- Other Models ----------

class DeltaSyncState(Base):
    __tablename__ = "delta_sync_state"
    id = Column(Integer, primary_key=True)
    last_full_sync = Column(DateTime)
    last_delta_sync = Column(DateTime)

class QueryCount(Base):
    __tablename__ = "query_counts"
    ticker = Column(String(50), primary_key=True)  # Here ticker refers to the AssetQuote.ticker (composite ticker)
    asset_type = Column(String(10), primary_key=True)
    count = Column(Integer, default=0)

# Create engine and session
engine = create_engine(DATABASE_URL, echo=False)
Base.metadata.create_all(engine)
Session = sessionmaker(bind=engine)

# Global Cache and Query Counter
latest_cache = {}
query_counter = Counter()
last_saved_counts = {}  # Holds last saved query counts

# ---------- Helper Functions ----------

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

# ---------- DataSource Helper ----------

def get_or_create_data_source(name, description=None):
    session = Session()
    try:
        ds = session.query(DataSource).filter_by(name=name).first()
        if not ds:
            ds = DataSource(name=name, description=description)
            session.add(ds)
            session.commit()
        return ds
    except SQLAlchemyError as e:
        session.rollback()
        logger.error(f"Error creating data source {name}: {e}")
        raise
    finally:
        session.close()

# Pre-populate Currency Assets (DataSources are now handled within functions)
def prepopulate_currency_assets():
    currencies = [
        ("USD", "US Dollar"),
        ("THB", "Thai Baht"),
        ("SGD", "Singapore Dollar"),
        ("USDT", "Tether USD")
    ]
    session = Session()
    try:
        for symbol, name in currencies:
            asset = session.query(CurrencyAsset).filter_by(asset_type="CURRENCY", symbol=symbol).first()
            if not asset:
                asset_currency = CurrencyAsset(asset_type="CURRENCY", symbol=symbol, name=name)
                session.add(asset_currency)
        session.commit()
    except SQLAlchemyError as e:
        session.rollback()
        logger.error(f"Error prepopulating currency assets: {e}")
        raise
    finally:
        session.close()

prepopulate_currency_assets()

# ---------- Data Fetching Functions for Stocks ----------

def fetch_yf_data_for_ticker(ticker, start_date=HISTORICAL_START_DATE, end_date=None):
    logger.info(f"Fetching data for stock ticker: {ticker}")
    try:
        data = yf.Ticker(ticker)
        hist = data.history(start=start_date, end=end_date)
        if hist.empty:
            return None, None
        quotes_df = pd.DataFrame([{
            "symbol": ticker,
            "longName": data.info.get("longName"),
            "displayName": data.info.get("displayName"),
            "language": data.info.get("language"),
            "region": data.info.get("region"),
            "quoteType": data.info.get("quoteType"),
            "exchange": data.info.get("exchange"),
            "fullExchangeName": data.info.get("fullExchangeName"),
            "first_trade_date": data.info.get("firstTradeDateEpochUtc")
        }])
        historical_data = {ticker: hist}
        return quotes_df, historical_data
    except Exception as e:
        logger.error(f"Error fetching data for {ticker}: {e}")
        return None, None

def fetch_yf_data(max_tickers_per_request, delay_t, query, start_date=HISTORICAL_START_DATE, end_date=None, sample_size=None):
    logger.info("Starting data fetch from yfinance for stocks...")
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

# ---------- Update Stock Data into New Models ----------

def update_stock_asset_and_quote(quotes_df, historical_data, upsert=False):
    session = Session()
    try:
        # Query or create DataSource for stocks (YFINANCE)
        data_source = session.query(DataSource).filter_by(name="yFinance").first()
        if not data_source:
            data_source = DataSource(name="yFinance", description="Yahoo Finance data source")
            session.add(data_source)
            session.commit()  # Commit to ensure the ID is assigned

        for idx, row in quotes_df.iterrows():
            ticker = row.get("symbol")
            if not ticker:
                continue
            # For stocks, the asset symbol and source_asset_key are the same (e.g. TSLA)
            name = row.get("longName") or row.get("displayName") or ticker
            language = row.get("language")
            region = row.get("region")
            exchange = row.get("exchange")
            full_exchange_name = row.get("fullExchangeName")
            first_trade = safe_convert(row.get("first_trade_date"), lambda x: datetime.datetime.fromtimestamp(x / 1000).date()) if row.get("first_trade_date") else None

            # Upsert base Asset for stock (using StockAsset)
            asset = session.query(Asset).filter_by(asset_type="STOCK", symbol=ticker).first()
            if not asset:
                asset = StockAsset(asset_type="STOCK", symbol=ticker, name=name, language=language,
                                   region=region, exchange=exchange, full_exchange_name=full_exchange_name,
                                   first_trade_date=first_trade, source_asset_key=ticker)
                session.add(asset)
            else:
                asset.name = name
                asset.source_asset_key = ticker
                if isinstance(asset, StockAsset):
                    asset.language = language
                    asset.region = region
                    asset.exchange = exchange
                    asset.full_exchange_name = full_exchange_name
                    asset.first_trade_date = first_trade

            # Determine quote currency based on exchange mapping
            exchange_currency_map = {
                "NMS": "USD",
                "NYQ": "USD",
                "SET": "THB"
            }
            quote_currency = exchange_currency_map.get(exchange, "USD")
            # Ensure currency asset exists
            currency_asset = session.query(CurrencyAsset).filter_by(asset_type="CURRENCY", symbol=quote_currency).first()
            if not currency_asset:
                currency_asset = CurrencyAsset(asset_type="CURRENCY", symbol=quote_currency, name=quote_currency)
                session.add(currency_asset)
            
            # Upsert AssetQuote (from stock asset to currency asset)
            # For stocks: composite ticker = source_asset_key + quote_currency, source_ticker = stock symbol (e.g. TSLA)
            composite_ticker = ticker + quote_currency
            asset_quote = session.query(AssetQuote).filter_by(ticker=composite_ticker, data_source_id=data_source.id).first()
            if not asset_quote:
                asset_quote = AssetQuote(
                    from_asset_type="STOCK",
                    from_asset_symbol=ticker,
                    to_asset_type="CURRENCY",
                    to_asset_symbol=quote_currency,
                    data_source_id=data_source.id,
                    ticker=composite_ticker,
                    source_ticker=ticker
                )
                session.add(asset_quote)
            else:
                asset_quote.source_ticker = ticker
            
            # Insert or update historical OHLCV data
            if ticker in historical_data:
                df = historical_data[ticker]
                for date, row_data in df.iterrows():
                    price_date = date if isinstance(date, datetime.datetime) else datetime.datetime.combine(date, datetime.time())
                    exists = session.query(AssetOHLCV).filter_by(asset_quote_id=asset_quote.id, price_date=price_date).first()
                    if exists:
                        if upsert:
                            exists.open_price = safe_convert(row_data.get("Open"), float)
                            exists.high_price = safe_convert(row_data.get("High"), float)
                            exists.low_price = safe_convert(row_data.get("Low"), float)
                            exists.close_price = safe_convert(row_data.get("Close"), float)
                            exists.volume = safe_convert(row_data.get("Volume"), Decimal)
                    else:
                        ohlcv = AssetOHLCV(
                            asset_quote=asset_quote,
                            price_date=price_date,
                            open_price=safe_convert(row_data.get("Open"), float),
                            high_price=safe_convert(row_data.get("High"), float),
                            low_price=safe_convert(row_data.get("Low"), float),
                            close_price=safe_convert(row_data.get("Close"), float),
                            volume=safe_convert(row_data.get("Volume"), Decimal)
                        )
                        session.add(ohlcv)
        session.commit()
    except SQLAlchemyError as e:
        session.rollback()
        logger.error(f"Error updating stock assets and quotes: {e}")
        raise
    finally:
        session.close()

# ---------- Data Fetching Functions for Crypto ----------

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
    url = "https://api.binance.com/api/v3/klines"
    
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

# ---------- Update Crypto Data into New Models ----------

def update_crypto_asset_and_quote(crypto_data, historical_data, upsert=False):
    session = Session()
    try:
        # Query or create DataSource for crypto (Binance)
        data_source = session.query(DataSource).filter_by(name="Binance").first()
        if not data_source:
            data_source = DataSource(name="Binance", description="Binance API data source")
            session.add(data_source)
            session.commit()  # Commit to ensure the ID is assigned

        for coin in crypto_data:
            # For crypto, use the uppercase symbol as the asset symbol and the coin_id as source_asset_key.
            coin_id = coin.get("id")  # e.g. "bitcoin"
            coin_symbol = coin.get("symbol").upper()  # e.g. "BTC"
            name = coin.get("name")
            image = coin.get("image")
            ath = safe_convert(coin.get("ath"), float)
            ath_date = pd.to_datetime(coin.get("ath_date")) if coin.get("ath_date") else None
            atl = safe_convert(coin.get("atl"), float)
            atl_date = pd.to_datetime(coin.get("atl_date")) if coin.get("atl_date") else None
            total_supply = safe_convert(coin.get("total_supply"), int)
            max_supply = safe_convert(coin.get("max_supply"), int)
            
            # Upsert base Asset for crypto (using CryptoAsset)
            asset = session.query(Asset).filter_by(asset_type="CRYPTO", symbol=coin_symbol).first()
            if not asset:
                asset = CryptoAsset(asset_type="CRYPTO", symbol=coin_symbol, name=name, image=image,
                                    ath=ath, ath_date=ath_date, atl=atl, atl_date=atl_date,
                                    total_supply=total_supply, max_supply=max_supply,
                                    source_asset_key=coin_id)
                session.add(asset)
            else:
                asset.name = name
                asset.source_asset_key = coin_id
                if isinstance(asset, CryptoAsset):
                    asset.image = image
                    asset.ath = ath
                    asset.ath_date = ath_date
                    asset.atl = atl
                    asset.atl_date = atl_date
                    asset.total_supply = total_supply
                    asset.max_supply = max_supply
            
            # For crypto, assume the quote currency is always USDT
            quote_currency = "USDT"
            currency_asset = session.query(CurrencyAsset).filter_by(asset_type="CURRENCY", symbol=quote_currency).first()
            if not currency_asset:
                currency_asset = CurrencyAsset(asset_type="CURRENCY", symbol=quote_currency, name="Tether USD")
                session.add(currency_asset)
            
            # Upsert AssetQuote (from crypto asset to currency asset)
            # For crypto: composite ticker = asset.symbol + quote_currency, and source_ticker is used to query Binance.
            composite_ticker = coin_symbol + quote_currency  # e.g. "BTCUSDT"
            asset_quote = session.query(AssetQuote).filter_by(ticker=composite_ticker, data_source_id=data_source.id).first()
            if not asset_quote:
                asset_quote = AssetQuote(
                    from_asset_type="CRYPTO",
                    from_asset_symbol=coin_symbol,
                    to_asset_type="CURRENCY",
                    to_asset_symbol=quote_currency,
                    data_source_id=data_source.id,
                    ticker=composite_ticker,
                    source_ticker=composite_ticker
                )
                session.add(asset_quote)
            else:
                asset_quote.source_ticker = composite_ticker
            
            # Insert or update historical OHLCV data from Binance
            # Note: historical_data keys for crypto are based on coin_id.
            if coin_id in historical_data:
                df = historical_data[coin_id]
                for date, row_data in df.iterrows():
                    price_date = date if isinstance(date, datetime.datetime) else datetime.datetime.combine(date, datetime.time())
                    exists = session.query(AssetOHLCV).filter_by(asset_quote_id=asset_quote.id, price_date=price_date).first()
                    if exists:
                        if upsert:
                            exists.open_price = safe_convert(row_data.get("open"), float)
                            exists.high_price = safe_convert(row_data.get("high"), float)
                            exists.low_price = safe_convert(row_data.get("low"), float)
                            exists.close_price = safe_convert(row_data.get("close"), float)
                            exists.volume = safe_convert(row_data.get("volume"), Decimal)
                    else:
                        ohlcv = AssetOHLCV(
                            asset_quote=asset_quote,
                            price_date=price_date,
                            open_price=safe_convert(row_data.get("open"), float),
                            high_price=safe_convert(row_data.get("high"), float),
                            low_price=safe_convert(row_data.get("low"), float),
                            close_price=safe_convert(row_data.get("close"), float),
                            volume=safe_convert(row_data.get("volume"), Decimal)
                        )
                        session.add(ohlcv)
        session.commit()
    except SQLAlchemyError as e:
        session.rollback()
        logger.error(f"Error updating crypto assets and quotes: {e}")
        raise
    finally:
        session.close()

# ---------- Global Sync Functions ----------

def full_sync_stocks():
    logger.info("Starting Global Full Sync for Stocks...")
    query_th = yf.EquityQuery("eq", ["region", "th"])
    quotes_df_th, historical_data_th = fetch_yf_data(MAX_TICKERS_PER_REQUEST, REQUEST_DELAY_SECONDS, query_th, start_date=HISTORICAL_START_DATE)
    query_us = yf.EquityQuery("is-in", ["exchange", "NMS", "NYQ"])
    quotes_df_us, historical_data_us = fetch_yf_data(MAX_TICKERS_PER_REQUEST, REQUEST_DELAY_SECONDS, query_us, start_date=HISTORICAL_START_DATE)
    quotes_df = pd.concat([quotes_df_th, quotes_df_us], ignore_index=True)
    historical_data = {**historical_data_th, **historical_data_us}
    update_stock_asset_and_quote(quotes_df, historical_data, upsert=False)
    session = Session()
    try:
        state = session.query(DeltaSyncState).filter_by(id=1).first()
        if not state:
            state = DeltaSyncState(id=1)
        state.last_full_sync = datetime.datetime.now()
        session.merge(state)
        session.commit()
    except SQLAlchemyError as e:
        session.rollback()
        logger.error(f"Error updating delta sync state for stocks full sync: {e}")
        raise
    finally:
        session.close()
    logger.info("Global Full Sync for Stocks Completed.")

def delta_sync_stocks():
    logger.info("Starting Global Delta Sync for Stocks...")
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
    update_stock_asset_and_quote(quotes_df, historical_data, upsert=True)
    session = Session()
    try:
        state = session.query(DeltaSyncState).filter_by(id=1).first()
        if not state:
            state = DeltaSyncState(id=1)
        state.last_delta_sync = datetime.datetime.now()
        session.merge(state)
        session.commit()
    except SQLAlchemyError as e:
        session.rollback()
        logger.error(f"Error updating delta sync state for stocks delta sync: {e}")
        raise
    finally:
        session.close()
    logger.info("Global Delta Sync for Stocks Completed.")

def full_sync_crypto():
    logger.info("Starting Global Full Sync for Cryptocurrencies...")
    crypto_data = fetch_coingecko_data()
    historical_data = {}
    for coin in crypto_data:
        coin_id = coin.get("id")
        # For crypto, we use the composite ticker from the asset symbol (which is coin['symbol'].upper()) + "USDT"
        symbol = coin.get("symbol").upper() + "USDT"
        df = fetch_binance_crypto_data(symbol, HISTORICAL_START_DATE, None)
        historical_data[coin_id] = df
        time.sleep(REQUEST_DELAY_SECONDS)
    update_crypto_asset_and_quote(crypto_data, historical_data, upsert=False)
    session = Session()
    try:
        state = session.query(DeltaSyncState).filter_by(id=1).first()
        if not state:
            state = DeltaSyncState(id=1)
        state.last_full_sync = datetime.datetime.now()
        session.merge(state)
        session.commit()
    except SQLAlchemyError as e:
        session.rollback()
        logger.error(f"Error updating delta sync state for crypto full sync: {e}")
        raise
    finally:
        session.close()
    logger.info("Global Full Sync for Cryptocurrencies Completed.")

def delta_sync_crypto():
    logger.info("Starting Global Delta Sync for Cryptocurrencies...")
    session = Session()
    state = session.query(DeltaSyncState).filter_by(id=1).first()
    session.close()
    today = datetime.datetime.now().date()
    two_days_ago = today - datetime.timedelta(days=2)
    crypto_data = fetch_coingecko_data()
    historical_data = {}
    for coin in crypto_data:
        coin_id = coin.get("id")
        symbol = coin.get("symbol").upper() + "USDT"
        df = fetch_binance_crypto_data(symbol, two_days_ago.strftime("%Y-%m-%d"), today.strftime("%Y-%m-%d"))
        historical_data[coin_id] = df
        time.sleep(REQUEST_DELAY_SECONDS)
    update_crypto_asset_and_quote(crypto_data, historical_data, upsert=True)
    session = Session()
    try:
        state = session.query(DeltaSyncState).filter_by(id=1).first()
        if not state:
            state = DeltaSyncState(id=1)
        state.last_delta_sync = datetime.datetime.now()
        session.merge(state)
        session.commit()
    except SQLAlchemyError as e:
        session.rollback()
        logger.error(f"Error updating delta sync state for crypto delta sync: {e}")
        raise
    finally:
        session.close()
    logger.info("Global Delta Sync for Cryptocurrencies Completed.")

# ---------- Data Source Classes for Latest Price Fetching ----------

class StockDataSource:
    @staticmethod
    def get_latest_price(ticker):
        try:
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
    BASE_URL = "https://api.binance.com/api/v3"

    @staticmethod
    def get_all_latest_prices():
        url = f"{CryptoDataSource.BASE_URL}/ticker/price"
        try:
            response = requests.get(url)
            if response.status_code == 200:
                data = response.json()
                # Return mapping keyed by Binance symbol (e.g. "BTCUSDT")
                return { item["symbol"]: float(item["price"]) for item in data }
            return {}
        except Exception as e:
            logger.error("Error fetching crypto prices: " + str(e))
            return {}

    @staticmethod
    def get_latest_price(ticker):
        # ticker should be like "BTCUSDT"
        url = f"{CryptoDataSource.BASE_URL}/ticker/price"
        params = {"symbol": ticker}
        try:
            response = requests.get(url, params=params)
            if response.status_code == 200:
                data = response.json()
                return float(data["price"])
            return "NOT_FOUND"
        except Exception as e:
            logger.error(f"Error fetching latest price for crypto {ticker}: {e}")
            return None

def get_latest_price(ticker, asset_type="STOCK"):
    session = Session()
    try:
        asset_quote = session.query(AssetQuote).filter_by(ticker=ticker).first()
        if not asset_quote:
            return "NOT_FOUND"
        ds_name = asset_quote.data_source.name.upper() if asset_quote.data_source else "UNKNOWN"
        source_ticker = asset_quote.source_ticker
    except SQLAlchemyError as e:
        logger.error(f"Error fetching asset_quote for ticker {ticker}: {e}")
        return "FETCH_ERROR"
    finally:
        session.close()

    key = (ds_name, source_ticker)
    now = datetime.datetime.now()
    if key in latest_cache:
        value, timestamp = latest_cache[key]
        if value == "NOT_FOUND" and (now - timestamp).total_seconds() / 60 < NOT_FOUND_TTL:
            return "NOT_FOUND"
        elif value is not None and (now - timestamp).total_seconds() / 60 < REGULAR_TTL:
            return value
    if asset_type.upper() == "STOCK":
        price = StockDataSource.get_latest_price(source_ticker)
    else:
        price = CryptoDataSource.get_latest_price(source_ticker)
    if price == "NOT_FOUND":
        latest_cache[key] = ("NOT_FOUND", now)
        return "NOT_FOUND"
    elif price is not None:
        latest_cache[key] = (price, now)
        return price
    return "FETCH_ERROR"

def refresh_stock_top_n_tickers():
    session = Session()
    try:
        # Get composite tickers for top stock queries from query_counter
        top_keys = [t[1] for t, count in query_counter.most_common(TOP_N_TICKERS) if t[0] == "STOCK"]
        asset_quotes = session.query(AssetQuote).filter(AssetQuote.ticker.in_(top_keys)).all()
    finally:
        session.close()
    source_tickers = [aq.source_ticker for aq in asset_quotes]
    prices = StockDataSource.refresh_latest_prices(source_tickers)
    now = datetime.datetime.now()
    ds_name = "YFINANCE"
    for st in source_tickers:
        if st in prices:
            latest_cache[(ds_name, st)] = (prices[st], now)
    time.sleep(REQUEST_DELAY_SECONDS)

def refresh_crypto_prices():
    prices = CryptoDataSource.get_all_latest_prices()
    now = datetime.datetime.now()
    ds_name = "BINANCE"
    for ticker, price in prices.items():
        latest_cache[(ds_name, ticker)] = (price, now)

def refresh_all_latest_prices():
    refresh_stock_top_n_tickers()
    refresh_crypto_prices()
    global last_cache_refresh
    last_cache_refresh = datetime.datetime.now()

# ---------- Query Counter Persistence ----------

def load_query_counter():
    session = Session()
    try:
        query_counts = session.query(QueryCount).all()
        for qc in query_counts:
            key = (qc.ticker, qc.asset_type)
            query_counter[key] = qc.count
            last_saved_counts[key] = qc.count
    except SQLAlchemyError as e:
        logger.error(f"Error loading query counter: {e}")
        raise
    finally:
        session.close()

def save_query_counter():
    session = Session()
    try:
        for (ticker, asset_type), current_count in query_counter.items():
            key = (ticker, asset_type)
            baseline = last_saved_counts.get(key, 0)
            delta = current_count - baseline
            if delta > 0:
                existing = session.query(QueryCount).filter_by(ticker=ticker, asset_type=asset_type).first()
                if existing:
                    existing.count += delta
                else:
                    session.add(QueryCount(ticker=ticker, asset_type=asset_type, count=current_count))
                last_saved_counts[key] = current_count
        session.commit()
    except SQLAlchemyError as e:
        session.rollback()
        logger.error(f"Error saving query counter: {e}")
        raise
    finally:
        session.close()

# ---------- Flask Application ----------

app = Flask(__name__)
api_stats = Counter()

@app.route("/api/unified")
def get_unified_ticker():
    ticker = request.args.get("ticker")
    if not ticker:
        return jsonify({"error": "Ticker parameter is required"}), 400
    session = Session()
    try:
        asset_quote = session.query(AssetQuote).filter_by(ticker=ticker).first()
        if not asset_quote:
            return jsonify({"error": "Ticker not found"}), 404
        ohlcv_records = session.query(AssetOHLCV).filter_by(asset_quote_id=asset_quote.id).all()
        # Use data source name and source_ticker for latest cache lookup.
        ds_key = (asset_quote.data_source.name.upper() if asset_quote.data_source else "UNKNOWN", asset_quote.source_ticker)
        cache_entry = latest_cache.get(ds_key, (None, None))
        unified_data = {
            "ticker": asset_quote.ticker,
            "source_ticker": asset_quote.source_ticker,
            "data_source": asset_quote.data_source.name if asset_quote.data_source else None,
            "from_asset": {
                "asset_type": asset_quote.from_asset_type,
                "symbol": asset_quote.from_asset_symbol,
            },
            "to_asset": {
                "asset_type": asset_quote.to_asset_type,
                "symbol": asset_quote.to_asset_symbol,
            },
            "latest_cache": {
                "price": cache_entry[0],
                "timestamp": cache_entry[1].isoformat() if cache_entry[1] else None
            },
            "historical_data": [
                {
                    "date": record.price_date.isoformat(),
                    "open": float(record.open_price) if record.open_price is not None else None,
                    "high": float(record.high_price) if record.high_price is not None else None,
                    "low": float(record.low_price) if record.low_price is not None else None,
                    "close": float(record.close_price) if record.close_price is not None else None,
                    "volume": float(record.volume) if record.volume is not None else None,
                }
                for record in ohlcv_records
            ]
        }
        return jsonify(unified_data)
    except SQLAlchemyError as e:
        logger.error(f"Error fetching unified ticker data: {e}")
        return jsonify({"error": "Database error"}), 500
    finally:
        session.close()

@app.route("/api/data_quality")
def data_quality():
    session = Session()
    try:
        total_assets = session.query(Asset).count()
        total_asset_quotes = session.query(AssetQuote).count()
        total_ohlcv = session.query(AssetOHLCV).count()
        missing_name_assets = session.query(Asset).filter(Asset.name.is_(None)).count()
        data_quality_metrics = {
            "total_assets": total_assets,
            "total_asset_quotes": total_asset_quotes,
            "total_ohlcv_records": total_ohlcv,
            "missing_name_assets": missing_name_assets
        }
        return jsonify(data_quality_metrics)
    except SQLAlchemyError as e:
        logger.error(f"Error fetching data quality metrics: {e}")
        return jsonify({"error": "Database error"}), 500
    finally:
        session.close()

@app.route("/api/ticker_traffic")
def ticker_traffic():
    data = [{"ticker": t[1], "asset_type": t[0], "count": count} for t, count in query_counter.most_common()]
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
    session = Session()
    try:
        asset_quote = session.query(AssetQuote).filter_by(ticker=ticker).first()
        if asset_quote:
            ds_key = (asset_quote.data_source.name.upper() if asset_quote.data_source else "UNKNOWN", asset_quote.source_ticker)
        else:
            ds_key = (None, None)
    finally:
        session.close()
    timestamp = latest_cache.get(ds_key, (None, datetime.datetime.now()))[1]
    if isinstance(result, (int, float)):
        return jsonify({
            "ticker": ticker,
            "asset_type": asset_type,
            "price": result,
            "timestamp": timestamp.isoformat() if timestamp else None
        })
    elif result == "NOT_FOUND":
        return jsonify({"error": "Ticker not found"}), 404
    else:
        return jsonify({"error": "Unable to fetch latest price"}), 500

@app.route("/api/assets")
def get_assets():
    asset_type = request.args.get("asset_type", None)
    session = Session()
    try:
        if asset_type:
            assets = session.query(Asset).filter_by(asset_type=asset_type.upper()).all()
        else:
            assets = session.query(Asset).all()
        asset_list = [
            {
                "asset_type": asset.asset_type,
                "symbol": asset.symbol,
                "name": asset.name,
                "source_asset_key": asset.source_asset_key
            }
            for asset in assets
        ]
        return jsonify(asset_list)
    except SQLAlchemyError as e:
        logger.error(f"Error fetching assets: {e}")
        return jsonify({"error": "Database error"}), 500
    finally:
        session.close()

@app.route("/api/historical")
def get_historical():
    ticker = request.args.get("ticker")
    if not ticker:
        return jsonify({"error": "Ticker parameter is required"}), 400
    session = Session()
    try:
        asset_quote = session.query(AssetQuote).filter_by(ticker=ticker).first()
        if not asset_quote:
            return jsonify({"error": "No historical data found for ticker"}), 404
        records = session.query(AssetOHLCV).filter_by(asset_quote_id=asset_quote.id).all()
        data = [
            {
                "date": record.price_date.isoformat(),
                "open": float(record.open_price) if record.open_price is not None else None,
                "high": float(record.high_price) if record.high_price is not None else None,
                "low": float(record.low_price) if record.low_price is not None else None,
                "close": float(record.close_price) if record.close_price is not None else None,
                "volume": float(record.volume) if record.volume is not None else None,
            }
            for record in records
        ]
        return jsonify({"ticker": ticker, "historical_data": data})
    except SQLAlchemyError as e:
        logger.error(f"Error fetching historical data: {e}")
        return jsonify({"error": "Database error"}), 500
    finally:
        session.close()

@app.route("/api/stats")
def get_stats():
    session = Session()
    try:
        total_assets = session.query(Asset).count()
        total_asset_quotes = session.query(AssetQuote).count()
        total_ohlcv = session.query(AssetOHLCV).count()
        delta_sync_state_count = session.query(DeltaSyncState).count()
        query_counts_count = session.query(QueryCount).count()
        state = session.query(DeltaSyncState).filter_by(id=1).first()
        db_file = os.path.join('instance', 'stock_data.db')
        if os.path.exists(db_file):
            db_size = os.path.getsize(db_file) / (1024 * 1024)
            db_size_str = f"{db_size:.2f} MB" if db_size < 1024 else f"{db_size / 1024:.2f} GB"
        else:
            db_size_str = "Database file not found"
        stats = {
            "total_assets": total_assets,
            "total_asset_quotes": total_asset_quotes,
            "total_ohlcv_records": total_ohlcv,
            "db_size": db_size_str,
            "cache_hit_rate": "100%",
            "api_requests_24h": sum(api_stats.values()),
            "table_records": {
                "assets": total_assets,
                "asset_quotes": total_asset_quotes,
                "asset_ohlcv": total_ohlcv,
                "delta_sync_state": delta_sync_state_count,
                "query_counts": query_counts_count
            },
            "last_full_sync": state.last_full_sync.isoformat() if state and state.last_full_sync else None,
            "last_delta_sync": state.last_delta_sync.isoformat() if state and state.last_delta_sync else None,
            "cache_size": len(latest_cache),
            "api_stats": dict(api_stats)
        }
        return jsonify(stats)
    except SQLAlchemyError as e:
        logger.error(f"Error fetching stats: {e}")
        return jsonify({"error": "Database error"}), 500
    finally:
        session.close()

@app.route("/api/tickers")
def get_tickers():
    query = request.args.get("query", "").strip().lower()
    if not query:
        return jsonify({"error": "Query parameter is required"}), 400

    asset_type = request.args.get("asset_type", None)
    try:
        limit = int(request.args.get("limit", 10))
        page = int(request.args.get("page", 1))
        limit = min(limit, MAX_TICKERS_PER_REQUEST)
        offset = (page - 1) * limit
    except ValueError:
        return jsonify({"error": "Invalid pagination parameters"}), 400

    fuzzy_enabled = request.args.get("fuzzy", "false").lower() == "true"
    session = Session()
    try:
        base_query = session.query(AssetQuote)
        if asset_type:
            base_query = base_query.filter(AssetQuote.from_asset_type == asset_type.upper())
        base_query = base_query.filter(
            (AssetQuote.ticker.ilike(f"%{query}%")) | (AssetQuote.source_ticker.ilike(f"%{query}%"))
        )
        if fuzzy_enabled:
            candidate_results = base_query.limit(50).all()
            scored_results = []
            for record in candidate_results:
                score = max(
                    fuzz.token_set_ratio(query, record.ticker.lower()),
                    fuzz.token_set_ratio(query, record.source_ticker.lower())
                )
                scored_results.append((score, record))
            scored_results.sort(key=lambda x: x[0], reverse=True)
            final_results = [record for _, record in scored_results[offset: offset + limit]]
        else:
            final_results = base_query.offset(offset).limit(limit).all()
        response = [
            {"ticker": r.ticker, "source_ticker": r.source_ticker}
            for r in final_results
        ]
        return jsonify(response)
    except SQLAlchemyError as e:
        logger.error(f"Error fetching tickers: {e}")
        return jsonify({"error": "Database error"}), 500
    finally:
        session.close()

# ---------- Updated Force Sync Endpoints with Data Source Parameter ----------

@app.route("/api/sync/full", methods=["POST"])
def sync_full():
    data = request.get_json() or {}
    ticker = data.get("ticker")
    asset_type = data.get("asset_type", "STOCK").upper()
    data_source = data.get("data_source")
    if not data_source:
        data_source = "YFINANCE" if asset_type == "STOCK" else "BINANCE" if asset_type == "CRYPTO" else None
    try:
        if ticker:
            if asset_type == "STOCK":
                if data_source.upper() != "YFINANCE":
                    return jsonify({"error": "Invalid data source for STOCK. Supported: YFINANCE"}), 400
                quotes_df, historical_data = fetch_yf_data_for_ticker(ticker)
                if quotes_df is not None and historical_data is not None:
                    update_stock_asset_and_quote(quotes_df, historical_data, upsert=True)
                    return jsonify({"message": f"Full sync for stock ticker {ticker} completed using {data_source}."})
                else:
                    return jsonify({"error": f"Failed to fetch data for stock ticker {ticker}"}), 404
            elif asset_type == "CRYPTO":
                if data_source.upper() != "BINANCE":
                    return jsonify({"error": "Invalid data source for CRYPTO. Supported: BINANCE"}), 400
                coins = fetch_coingecko_data()
                coin_data = next((coin for coin in coins if coin.get("id", "").lower() == ticker.lower()), None)
                if coin_data:
                    symbol = coin_data["symbol"].upper() + "USDT"
                    historical_data = fetch_binance_crypto_data(symbol, HISTORICAL_START_DATE, None)
                    if historical_data is not None:
                        update_crypto_asset_and_quote([coin_data], {coin_data["id"]: historical_data}, upsert=True)
                        return jsonify({"message": f"Full sync for crypto ticker {ticker} completed using {data_source}."})
                    else:
                        return jsonify({"error": f"Failed to fetch historical data for crypto ticker {ticker}"}), 404
                else:
                    return jsonify({"error": f"Failed to fetch metadata for crypto ticker {ticker}"}), 404
            else:
                return jsonify({"error": "Invalid asset_type"}), 400
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
    data_source = data.get("data_source")
    if not data_source:
        data_source = "YFINANCE" if asset_type == "STOCK" else "BINANCE" if asset_type == "CRYPTO" else None
    try:
        if ticker:
            today = datetime.datetime.now().date()
            two_days_ago = today - datetime.timedelta(days=2)
            if asset_type == "STOCK":
                if data_source.upper() != "YFINANCE":
                    return jsonify({"error": "Invalid data source for STOCK. Supported: YFINANCE"}), 400
                quotes_df, historical_data = fetch_yf_data_for_ticker(ticker, start_date=two_days_ago.strftime("%Y-%m-%d"), end_date=today.strftime("%Y-%m-%d"))
                if quotes_df is not None and historical_data is not None:
                    update_stock_asset_and_quote(quotes_df, historical_data, upsert=True)
                    return jsonify({"message": f"Delta sync for stock ticker {ticker} completed using {data_source}."})
                else:
                    return jsonify({"error": f"Failed to fetch delta data for stock ticker {ticker}"}), 404
            elif asset_type == "CRYPTO":
                if data_source.upper() != "BINANCE":
                    return jsonify({"error": "Invalid data source for CRYPTO. Supported: BINANCE"}), 400
                coins = fetch_coingecko_data()
                coin_data = next((coin for coin in coins if coin.get("id", "").lower() == ticker.lower()), None)
                if coin_data:
                    symbol = coin_data["symbol"].upper() + "USDT"
                    historical_data = fetch_binance_crypto_data(symbol, two_days_ago.strftime("%Y-%m-%d"), today.strftime("%Y-%m-%d"))
                    if historical_data is not None:
                        update_crypto_asset_and_quote([coin_data], {coin_data["id"]: historical_data}, upsert=True)
                        return jsonify({"message": f"Delta sync for crypto ticker {ticker} completed using {data_source}."})
                    else:
                        return jsonify({"error": f"Failed to fetch delta historical data for crypto ticker {ticker}"}), 404
                else:
                    return jsonify({"error": f"Failed to fetch metadata for crypto ticker {ticker}"}), 404
            else:
                return jsonify({"error": "Invalid asset_type"}), 400
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

# ---------- Scheduler Setup ----------

scheduler = BackgroundScheduler()
scheduler.add_job(refresh_all_latest_prices, "interval", minutes=LATEST_CACHE_REFRESH_INTERVAL_MINUTES, id="cache_refresh")
scheduler.add_job(delta_sync_stocks, "interval", days=DELTA_SYNC_INTERVAL_DAYS, id="delta_sync_stocks")
scheduler.add_job(delta_sync_crypto, "interval", days=DELTA_SYNC_INTERVAL_DAYS, id="delta_sync_crypto")
scheduler.add_job(save_query_counter, "interval", minutes=QUERY_COUNTER_SAVE_INTERVAL_MINUTES, id="save_query_counter")
scheduler.start()

load_query_counter()

if __name__ == "__main__":
    session = Session()
    try:
        assets_count = session.query(Asset).count()
        asset_quotes_count = session.query(AssetQuote).count()
        if assets_count == 0 or asset_quotes_count == 0:
            Base.metadata.drop_all(engine)
            Base.metadata.create_all(engine)
    except SQLAlchemyError as e:
        logger.error(f"Error checking database counts: {e}")
        raise
    finally:
        session.close()
    # Pre-populate cache before starting to serve user requests
    refresh_all_latest_prices()
    app.run(host=FLASK_HOST, port=FLASK_PORT)
