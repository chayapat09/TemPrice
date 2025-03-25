Below is one way to redesign the schema so that the “Asset” (the underlying entity like Bitcoin, Tesla, THB, etc.) is separated from the “Quote” (the specific price pairing, e.g. TSLA in USD, BTC/USDT, USDTHB). This design keeps all the metadata you currently have for each asset class and allows you to add multiple quotes (in different quote currencies) for a single asset later.

1. Asset Table
This table stores the intrinsic properties of an asset. Each asset is defined only once regardless of how many quote pairs it has. You can either use one table with many nullable columns or use table inheritance (or extension tables) for type-specific metadata. For example:
	•	Common Columns:
	◦	id (Primary Key)
	◦	asset_type (ENUM or string: e.g. STOCK, CRYPTO, CURRENCY)
	◦	symbol (Base symbol for the asset, e.g. "TSLA", "BTC", "THB")
	◦	name (Asset name)
	•	Type-Specific Metadata (example columns):
	◦	For Stocks:
	▪	language
	▪	region
	▪	exchange (e.g. "NMS", "NYQ", "SET")
	▪	full_exchange_name
	▪	first_trade_date
	◦	For Cryptos:
	▪	image
	▪	ath (all-time high)
	▪	ath_date
	▪	atl (all-time low)
	▪	atl_date
	▪	total_supply
	▪	max_supply
	◦	For Currencies:
	▪	from_currency (typically "USD")
	▪	from_currency_name (e.g. "United States Dollar")
	▪	to_currency (e.g. "THB")
	▪	to_currency_name (e.g. "Thai Baht")
Example Row (Tesla):
id
asset_type
symbol
name
language
region
exchange
full_exchange_name
first_trade_date
...
1
STOCK
TSLA
Tesla Inc.
en
US
NMS
NASDAQ Global
2010-06-29
...

2. AssetQuote Table
This table represents the quote (i.e. the pricing pair) for a given asset. An asset can have one or more quotes in different quote currencies. The “ticker” here is used for market data (price data) and reflects the pair (e.g. "TSLA" for Tesla quoted in USD, "BTCUSDT" for Bitcoin quoted in USDT, "USDTHB" for currency pair).
	•	Columns:
	◦	id (Primary Key)
	◦	asset_id (Foreign Key to Asset.id)
	◦	quote_currency (The currency in which the asset is quoted, e.g. "USD", "USDT", "THB")
	◦	ticker (Unique identifier for price data, e.g. "TSLA", "BTCUSDT", "USDTHB", "SCC.BK")
	◦	exchange (For stocks, you can store the exchange code. This can then be used in your business logic to enforce mappings such as { NMS -> USD, NYQ -> USD, SET -> THB })
Example Row (Tesla Quote in USD):
id
asset_id
quote_currency
ticker
exchange
1
1
USD
TSLA
NMS
Example Row (Bitcoin Quote in USDT):
id
asset_id
quote_currency
ticker
exchange
2
2
USDT
BTCUSDT
(null)
Example Row (Thai Baht Currency Pair):
id
asset_id
quote_currency
ticker
exchange
3
3
THB
USDTHB
(null)

3. AssetPrice Table
This table stores historical or realtime pricing data for a given quote. Instead of using the ticker directly as the primary identifier, you can reference the quote record.
	•	Columns:
	◦	asset_quote_id (Foreign Key to AssetQuote.id) (Alternatively, if you prefer using the ticker string as the key, you can do so provided it’s unique.)
	◦	price_date (Date)
	◦	open_price
	◦	high_price
	◦	low_price
	◦	close_price
	◦	volume
A composite primary key of (asset_quote_id, price_date) can be used to ensure uniqueness.
Example Row (Tesla Price Data):
asset_quote_id
price_date
open_price
high_price
low_price
close_price
volume
1
2023-03-15
700.00
720.00
695.00
715.00
15,000,000

Benefits of This Design
	•	Separation of Concerns: The asset’s static metadata is stored in one place (the Asset table), while the market-specific quoting details and pricing data are stored separately. This makes it easier to support multiple quote currencies for a single asset.
	•	Extensibility: In the future, you can add additional quote pairs for a given asset without changing the asset’s metadata. For example, you might eventually support Tesla prices quoted in both USD and EUR.
	•	Metadata Preservation: By keeping asset-type–specific metadata in the Asset (or extended tables), you ensure that the rich information for stocks, cryptocurrencies, and currencies remains available and clearly separated from market data.
	•	Exchange Mapping: For stocks, you can enforce the rule that if the exchange is “NMS” or “NYQ”, then the quote currency is USD; if it is “SET”, then the quote currency is THB. This logic can be implemented in your application layer or enforced via lookup tables and constraints.

Summary Diagram (Conceptual)
+----------------+        +-------------------+        +-------------------+
|    Asset       |        |    AssetQuote     |        |    AssetPrice     |
+----------------+        +-------------------+        +-------------------+
| id (PK)        |<-------| id (PK)           |        | asset_quote_id    |
| asset_type     |        | asset_id (FK)     |        | price_date        |
| symbol         |        | quote_currency    |        | open_price        |
| name           |        | ticker            |        | high_price        |
| ... (metadata)|         | exchange          |        | low_price         |
+----------------+        +-------------------+        | close_price       |
                                                     | volume            |
                                                     +-------------------+
In this model, each asset can have multiple quotes (e.g. different currencies or exchange-specific representations), and each quote will have its own stream of price data.

This redesign allows you to list assets separately from their market quotes and supports future expansion (like adding new quote currencies) while keeping the rich metadata for each asset class intact.
Please Add DataSoruce Table (for example yFinance , Binance , alphavantage ... etc )and for Asset Price please add DataSoruce id as key for in future same AssetPrice can has same price but from different source , for Type Specfic Metadata please use interitance to do specilization and price date please use date time data type.
Below is an updated design that incorporates a dedicated DataSource table and refines the AssetPrice table so that each price record is also keyed by its source. In addition, we use inheritance (polymorphic mapping) for the type‐specific metadata of assets so that you can later extend the model for stocks, cryptos, currencies, etc.
1. Data Model Overview
DataSource Table
This table will hold information about the source of data (e.g. yFinance, Binance, AlphaVantage). It allows you to record, for any price record, which source provided the price data. Typical columns include:
	•	id: Primary key.
	•	name: Name of the data source (e.g. "yFinance", "Binance", "AlphaVantage").
	•	description: (Optional) Further details about the data source.
	•	base_url: (Optional) URL or endpoint reference.
Asset Table (with Inheritance for Type-Specific Metadata)
This table represents the underlying asset (for example, Tesla, Bitcoin, or THB). You’ll use a base class for common fields and then subclass it for stocks, crypto, and currency. For example:
	•	Common columns (in Asset base table):
	◦	id (Primary Key)
	◦	asset_type (e.g. "STOCK", "CRYPTO", "CURRENCY")
	◦	symbol (The base symbol, e.g. "TSLA", "BTC", "THB")
	◦	name (The asset’s full name)
	◦	discriminator column (for polymorphic identity)
	•	StockAsset (subclass):
	◦	language
	◦	region
	◦	exchange (e.g. "NMS", "NYQ", "SET")
	◦	full_exchange_name
	◦	first_trade_date
	•	CryptoAsset (subclass):
	◦	image
	◦	ath (all-time high)
	◦	ath_date
	◦	atl (all-time low)
	◦	atl_date
	◦	total_supply
	◦	max_supply
	•	CurrencyAsset (subclass):
	◦	from_currency (typically fixed to "USD")
	◦	from_currency_name (e.g. "United States Dollar")
	◦	to_currency
	◦	to_currency_name
AssetQuote Table
This table represents the quote information (or the pricing pair) for a given asset. In other words, while the Asset table stores the intrinsic metadata (e.g. “Tesla Inc.”), the AssetQuote represents how that asset is being traded or quoted (e.g. "TSLA" quoted in USD). Typical columns include:
	•	id (Primary Key)
	•	asset_id (Foreign key to Asset)
	•	quote_currency (The currency in which the asset is quoted; e.g. "USD", "THB", "USDT")
	•	ticker (Market identifier used for pricing; e.g. "TSLA", "BTCUSDT", "USDTHB")
	•	exchange (For stocks, this can help enforce rules like mapping "NMS" → USD, "SET" → THB, etc.)
AssetPrice Table (with DataSource Link and DateTime Field)
This table stores the historical or realtime price data. It now includes:
	•	A reference to the AssetQuote (via asset_quote_id).
	•	A reference to the DataSource (via data_source_id), so that the same price can be recorded from multiple sources.
	•	A price_datetime column using a DateTime data type (rather than just date) to capture the exact moment of the price record.
	•	Pricing fields (open, high, low, close, volume).
A composite primary key can be defined on (asset_quote_id, data_source_id, price_datetime) to ensure uniqueness.

2. Conceptual Diagram
+----------------+       +------------------+       +-------------------+       +-------------------+
|   DataSource   |       |      Asset       |       |    AssetQuote     |       |    AssetPrice     |
+----------------+       +------------------+       +-------------------+       +-------------------+
| id (PK)        |       | id (PK)          |<----->| id (PK)           |<----->| asset_quote_id    |
| name           |       | asset_type       |       | asset_id (FK)     |       | data_source_id (FK)|
| description    |       | symbol           |       | quote_currency    |       | price_datetime    |
| base_url       |       | name             |       | ticker            |       | open_price        |
+----------------+       | discriminator    |       | exchange          |       | high_price        |
                         | ...              |       +-------------------+       | low_price         |
                         +------------------+                                   | close_price       |
                                                                            | volume            |
                                                                            +-------------------+
Note:
	•	The Asset table uses inheritance (polymorphism) so that additional, type-specific fields (for stocks, crypto, and currencies) are stored in subclass tables or in a single table with nullable columns.
	•	The AssetPrice table’s composite key (asset_quote_id, data_source_id, price_datetime) ensures that you can store multiple price records even if the prices are the same but coming from different sources.

3. Example SQLAlchemy Models
Below is a simplified Python/SQLAlchemy snippet demonstrating the new tables and inheritance structure:
from sqlalchemy import (
    Column, String, Integer, DateTime, ForeignKey, DECIMAL, create_engine, func
)
from sqlalchemy.orm import relationship, sessionmaker, declarative_base
from sqlalchemy.ext.declarative import declared_attr

Base = declarative_base()

# DataSource Table
class DataSource(Base):
    __tablename__ = "data_sources"
    id = Column(Integer, primary_key=True)
    name = Column(String(50), unique=True, nullable=False)
    description = Column(String(200))
    base_url = Column(String(200))


# Asset Base with Single Table Inheritance (STI) example
class Asset(Base):
    __tablename__ = "assets"
    id = Column(Integer, primary_key=True)
    asset_type = Column(String(20), nullable=False)
    symbol = Column(String(20), nullable=False)
    name = Column(String(100))
    discriminator = Column(String(50))  # for polymorphic identity

    __mapper_args__ = {
        'polymorphic_on': discriminator,
        'polymorphic_identity': 'asset'
    }

# Stock-specific metadata
class StockAsset(Asset):
    __mapper_args__ = {'polymorphic_identity': 'stock'}
    language = Column(String(10))
    region = Column(String(10))
    exchange = Column(String(50))
    full_exchange_name = Column(String(100))
    first_trade_date = Column(DateTime)

# Crypto-specific metadata
class CryptoAsset(Asset):
    __mapper_args__ = {'polymorphic_identity': 'crypto'}
    image = Column(String(200))
    ath = Column(DECIMAL(15, 2))
    ath_date = Column(DateTime)
    atl = Column(DECIMAL(15, 2))
    atl_date = Column(DateTime)
    total_supply = Column(Integer)
    max_supply = Column(Integer)

# Currency-specific metadata
class CurrencyAsset(Asset):
    __mapper_args__ = {'polymorphic_identity': 'currency'}
    from_currency = Column(String(10), default="USD")
    from_currency_name = Column(String(100), default="United States Dollar")
    to_currency = Column(String(10))
    to_currency_name = Column(String(100))


# AssetQuote Table
class AssetQuote(Base):
    __tablename__ = "asset_quotes"
    id = Column(Integer, primary_key=True)
    asset_id = Column(Integer, ForeignKey("assets.id"), nullable=False)
    quote_currency = Column(String(10), nullable=False)
    ticker = Column(String(50), nullable=False, unique=True)
    exchange = Column(String(50))  # optional mapping for stocks
    asset = relationship("Asset", backref="quotes")


# AssetPrice Table (with DataSource link)
class AssetPrice(Base):
    __tablename__ = "asset_prices"
    asset_quote_id = Column(Integer, ForeignKey("asset_quotes.id"), primary_key=True)
    data_source_id = Column(Integer, ForeignKey("data_sources.id"), primary_key=True)
    price_datetime = Column(DateTime, primary_key=True)  # now using datetime instead of date
    open_price = Column(DECIMAL(10, 2))
    high_price = Column(DECIMAL(10, 2))
    low_price = Column(DECIMAL(10, 2))
    close_price = Column(DECIMAL(10, 2))
    volume = Column(DECIMAL(20, 8))
    
    asset_quote = relationship("AssetQuote", backref="prices")
    data_source = relationship("DataSource")

4. Benefits of the Updated Model
	•	Data Source Tracking: With a dedicated DataSource table and a foreign key in AssetPrice, you can easily store, compare, and even reconcile pricing data from multiple sources (e.g. yFinance vs. Binance).
	•	Flexible Price Records: By using a composite key that includes data_source_id and price_datetime, the model allows multiple price entries (possibly identical in value) from different providers for the same asset quote.
	•	Extensible Asset Metadata: Inheritance (via SQLAlchemy polymorphic mapping) lets you keep the common asset data in one table while extending each asset type (stocks, crypto, currencies) with additional fields. This preserves all metadata and makes it easier to evolve your model as needed.
	•	Clear Separation of Concepts: The separation of Asset (the underlying entity), AssetQuote (the quoting/pairing information), and AssetPrice (the time-series price data by source) provides clarity and flexibility for future extensions (such as adding new quote currencies).

This redesigned schema meets the requirements to track multiple price sources for the same asset pair and uses inheritance for type-specific asset metadata while recording precise price timestamps with a DateTime field.
for currency mapper_args = {'polymorphic_identity': 'currency'} from_currency = Column(String(10), default="USD") from_currency_name = Column(String(100), default="United States Dollar") to_currency = Column(String(10)) to_currency_name = Column(String(100))
for currency it asset shound't has from to because currency it self (THB USD SGD ...) is asset from , to data will use in it price (AssetPrice)
Also beware that quote_currency should be mapping to Asset (currency)
from model change above please apply to below code
--- Start of app.py --- import datetime import time import logging import os import io import pandas as pd import requests from collections import Counter from decimal import Decimal from flask import Flask, jsonify, request, render_template, current_app from sqlalchemy import BigInteger, Column, Date, DateTime, DECIMAL, Integer, String, create_engine, func, text, case from sqlalchemy.ext.declarative import declarative_base from sqlalchemy.orm import sessionmaker from apscheduler.schedulers.background import BackgroundScheduler from rapidfuzz import fuzz # for fuzzy matching from sqlalchemy.exc import SQLAlchemyError
Configurable Parameters
MAX_TICKERS_PER_REQUEST = 50 REQUEST_DELAY_SECONDS = 5 HISTORICAL_START_DATE = "2013-01-01" DATABASE_URL = "sqlite:///instance/stock_data.db" FLASK_HOST = "0.0.0.0" FLASK_PORT = 8082 TOP_N_TICKERS = 100 LATEST_CACHE_REFRESH_INTERVAL_MINUTES = 1 REGULAR_TTL = 15 NOT_FOUND_TTL = 1440 QUERY_COUNTER_SAVE_INTERVAL_MINUTES = 5 DELTA_SYNC_INTERVAL_DAYS = 1
New configuration for currency data (AlphaVantage)
ALPHAVANTAGE_API_KEY = "demo" # Replace with your own API key CURRENCY_LIST_URL = "https://www.alphavantage.co/physical_currency_list/"
Ensure the 'instance' directory exists
if not os.path.exists('instance'): os.makedirs('instance')
Logging Configuration
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s') logger = logging.getLogger(name)
Global Cache, Query Counter, and Baseline for last saved counts
latest_cache = {} query_counter = Counter() last_saved_counts = {} # This dictionary holds the last saved count for each key last_cache_refresh = None
SQLAlchemy Setup and Models
Base = declarative_base()
class BaseQuote(Base): abstract = True ticker = Column(String(50), primary_key=True) asset_type = Column(String(10), nullable=False, primary_key=True) symbol = Column(String(20), nullable=False) name = Column(String(100), nullable=True)
class StockQuote(BaseQuote): tablename = "stock_quotes" language = Column(String(10)) region = Column(String(10)) quote_type = Column(String(20)) exchange = Column(String(50)) full_exchange_name = Column(String(100)) first_trade_date = Column(Date)
class CryptoQuote(BaseQuote): tablename = "crypto_quotes" image = Column(String(200)) ath = Column(DECIMAL(15, 2)) ath_date = Column(DateTime) atl = Column(DECIMAL(15, 2)) atl_date = Column(DateTime) total_supply = Column(BigInteger) max_supply = Column(BigInteger)
class CurrencyQuote(BaseQuote): tablename = "currency_quotes" # New columns per the required structure from_currency = Column(String(10), default="USD") # always "USD" from_currency_name = Column(String(100), default="United States Dollar") # e.g. "United States Dollar" to_currency = Column(String(10)) # same as ticker to_currency_name = Column(String(100)) # from currency list or API metadata
class AssetPrice(Base): tablename = "asset_prices" ticker = Column(String(50), primary_key=True) asset_type = Column(String(10), primary_key=True) price_date = Column(Date, primary_key=True) open_price = Column(DECIMAL(10, 2)) high_price = Column(DECIMAL(10, 2)) low_price = Column(DECIMAL(10, 2)) close_price = Column(DECIMAL(10, 2)) volume = Column(DECIMAL(20, 8))
class DeltaSyncState(Base): tablename = "delta_sync_state" id = Column(Integer, primary_key=True) last_full_sync = Column(DateTime) last_delta_sync = Column(DateTime)
class QueryCount(Base): tablename = "query_counts" ticker = Column(String(50), primary_key=True) asset_type = Column(String(10), primary_key=True) count = Column(Integer, default=0)
Create engine and session
engine = create_engine(DATABASE_URL, echo=False) Base.metadata.create_all(engine) Session = sessionmaker(bind=engine)
Add missing columns for SQLite if necessary
with engine.connect() as conn: try: conn.execute(text("ALTER TABLE delta_sync_state ADD COLUMN last_full_sync DATETIME")) except Exception: pass try: conn.execute(text("ALTER TABLE delta_sync_state ADD COLUMN last_delta_sync DATETIME")) except Exception: pass
Helper Functions
def safe_convert(value, convert_func=lambda x: x): if value is None or pd.isna(value): return None try: return convert_func(value) except Exception: return None
def chunk_list(lst, chunk_size): for i in range(0, len(lst), chunk_size): yield lst[i:i + chunk_size]
---------------------------
Currency Data Helpers
---------------------------
def download_currency_list(): """Download the currency list CSV from the provided URL and return a list of dicts.""" try: response = requests.get(CURRENCY_LIST_URL) if response.status_code == 200: df = pd.read_csv(io.StringIO(response.text)) currencies = [] for _, row in df.iterrows(): code = str(row["currency code"]).strip() name = str(row["currency name"]).strip() currencies.append({ "ticker": code, "symbol": code, "name": name, "from_currency": "USD", # fixed value "from_currency_name": "United States Dollar", # fixed value "to_currency": code, # same as ticker "to_currency_name": name # from CSV data }) return currencies else: logger.error("Failed to download currency list: " + response.text) return [] except Exception as e: logger.error("Exception in downloading currency list: " + str(e)) return []
def fetch_alpha_realtime_currency_rate(to_currency, from_currency="USD"): """Fetch realtime exchange rate using AlphaVantage's CURRENCY_EXCHANGE_RATE API.""" url = "https://www.alphavantage.co/query" params = { "function": "CURRENCY_EXCHANGE_RATE", "from_currency": from_currency, "to_currency": to_currency, "apikey": ALPHAVANTAGE_API_KEY } try: response = requests.get(url, params=params, timeout=10) if response.status_code == 200: data = response.json() rate_info = data.get("Realtime Currency Exchange Rate", {}) if rate_info: rate = rate_info.get("5. Exchange Rate") if rate: return float(rate) else: logger.error(f"Error fetching realtime currency rate for {to_currency}: {response.text}") except Exception as e: logger.error(f"Exception fetching realtime currency rate for {to_currency}: {e}") return "NOT_FOUND"
def fetch_alpha_fx_daily(from_symbol, to_symbol, start_date, end_date, outputsize="compact"): """Fetch historical FX daily data using AlphaVantage's FX_DAILY API and return a DataFrame.""" url = "https://www.alphavantage.co/query" params = { "function": "FX_DAILY", "from_symbol": from_symbol, "to_symbol": to_symbol, "apikey": ALPHAVANTAGE_API_KEY, "outputsize": outputsize, "datatype": "json" } try: response = requests.get(url, params=params, timeout=10) if response.status_code == 200: data = response.json() time_series = data.get("Time Series FX (Daily)", {}) if not time_series: return pd.DataFrame() records = [] for date_str, day_data in time_series.items(): date_obj = datetime.datetime.strptime(date_str, "%Y-%m-%d").date() if start_date and date_obj < datetime.datetime.strptime(start_date, "%Y-%m-%d").date(): continue if end_date and date_obj > datetime.datetime.strptime(end_date, "%Y-%m-%d").date(): continue records.append({ "date": date_obj, "open": float(day_data["1. open"]), "high": float(day_data["2. high"]), "low": float(day_data["3. low"]), "close": float(day_data["4. close"]), "volume": None # FX data does not typically include volume. }) if records: df = pd.DataFrame(records) df.sort_values("date", inplace=True) df.set_index("date", inplace=True) return df else: logger.error(f"Error fetching FX daily data for {to_symbol}: {response.text}") except Exception as e: logger.error(f"Exception fetching FX daily data for {to_symbol}: {e}") return pd.DataFrame()
def update_currency_database(currency_data, historical_data, upsert=False): """Insert or update currency quotes and their historical FX data in the database.""" session = Session() currency_quote_mappings = [] for item in currency_data: mapping = { "ticker": item["ticker"], "asset_type": "CURRENCY", "symbol": item["symbol"], "name": item["name"], "from_currency": item.get("from_currency", "USD"), "from_currency_name": item.get("from_currency_name", "United States Dollar"), "to_currency": item.get("to_currency"), "to_currency_name": item.get("to_currency_name") } currency_quote_mappings.append(mapping) if upsert: for mapping in currency_quote_mappings: session.merge(CurrencyQuote(**mapping)) session.commit() else: session.bulk_insert_mappings(CurrencyQuote, currency_quote_mappings) session.commit() currency_price_mappings = [] for ticker, df in historical_data.items(): if df is None or df.empty: continue for date, data_row in df.iterrows(): price_date = date if isinstance(date, datetime.date) else date.date() mapping = { "ticker": ticker, "asset_type": "CURRENCY", "price_date": price_date, "open_price": safe_convert(data_row.get("open"), float), "high_price": safe_convert(data_row.get("high"), float), "low_price": safe_convert(data_row.get("low"), float), "close_price": safe_convert(data_row.get("close"), float), "volume": None } currency_price_mappings.append(mapping) if upsert: for mapping in currency_price_mappings: session.merge(AssetPrice(**mapping)) session.commit() else: session.bulk_insert_mappings(AssetPrice, currency_price_mappings) session.commit() session.close()
def full_sync_currency(): """Perform a full sync for all currency pairs (from USD to each currency in the list).""" logger.info("Starting Full Sync for Currencies...") currency_list = download_currency_list() historical_data = {} for currency in currency_list: ticker = currency["ticker"] if ticker.upper() == "USD": continue # Skip USD as USD/USD is always 1 df = fetch_alpha_fx_daily("USD", ticker, HISTORICAL_START_DATE, None, outputsize="full") historical_data[ticker] = df time.sleep(REQUEST_DELAY_SECONDS) update_currency_database(currency_list, historical_data, upsert=False) session = Session() state = session.query(DeltaSyncState).filter_by(id=2).first() if not state: state = DeltaSyncState(id=2) state.last_full_sync = datetime.datetime.now() session.merge(state) session.commit() session.close() logger.info("Full Sync for Currencies Completed.")
def delta_sync_currency(): """Perform a delta sync (last 2 days) for all currencies.""" logger.info("Starting Delta Sync for Currencies...") session = Session() state = session.query(DeltaSyncState).filter_by(id=2).first() session.close() today = datetime.datetime.now().date() two_days_ago = today - datetime.timedelta(days=2) currency_list = download_currency_list() historical_data = {} for currency in currency_list: ticker = currency["ticker"] if ticker.upper() == "USD": continue df = fetch_alpha_fx_daily("USD", ticker, two_days_ago.strftime("%Y-%m-%d"), today.strftime("%Y-%m-%d"), outputsize="compact") historical_data[ticker] = df time.sleep(REQUEST_DELAY_SECONDS) update_currency_database(currency_list, historical_data, upsert=True) session = Session() state = session.query(DeltaSyncState).filter_by(id=2).first() if not state: state = DeltaSyncState(id=2) state.last_delta_sync = datetime.datetime.now() session.merge(state) session.commit() session.close() logger.info("Delta Sync for Currencies Completed.")
class CurrencyDataSource: BASE_URL = "https://www.alphavantage.co/query"
@staticmethod
def get_latest_price(ticker):
    return fetch_alpha_realtime_currency_rate(ticker, from_currency="USD")

@staticmethod
def get_all_latest_prices():
    currency_list = download_currency_list()
    prices = {}
    for currency in currency_list:
        ticker = currency["ticker"]
        if ticker.upper() == "USD":
            prices[ticker] = 1.0
        else:
            price = fetch_alpha_realtime_currency_rate(ticker, from_currency="USD")
            prices[ticker] = price
        time.sleep(REQUEST_DELAY_SECONDS)
    return prices
def refresh_currency_prices(): prices = CurrencyDataSource.get_all_latest_prices() now = datetime.datetime.now() for ticker, price in prices.items(): latest_cache[("CURRENCY", ticker)] = (price, now)
---------------------------
Stock & Crypto Functions (unchanged)
---------------------------
def fetch_yf_data_for_ticker(ticker, start_date=HISTORICAL_START_DATE, end_date=None): logger.info(f"Fetching data for stock ticker: {ticker}") try: import yfinance as yf data = yf.Ticker(ticker) hist = data.history(start=start_date, end=end_date) if hist.empty: return None, None quotes_df = pd.DataFrame([{ "symbol": ticker, "longName": data.info.get("longName"), "displayName": data.info.get("displayName"), "language": data.info.get("language"), "region": data.info.get("region"), "quoteType": data.info.get("quoteType"), "exchange": data.info.get("exchange"), "fullExchangeName": data.info.get("fullExchangeName"), "firstTradeDateMilliseconds": data.info.get("firstTradeDateEpochUtc") }]) historical_data = {ticker: hist} return quotes_df, historical_data except Exception as e: logger.error(f"Error fetching data for {ticker}: {e}") return None, None
def fetch_yf_data(max_tickers_per_request, delay_t, query, start_date=HISTORICAL_START_DATE, end_date=None, sample_size=None): logger.info("Starting data fetch from yfinance for stocks...") import yfinance as yf all_quotes = [] offset = 0 size = sample_size if sample_size is not None else 250 if sample_size is not None: result = yf.screen(query, offset=0, size=sample_size) quotes = result.get("quotes", []) all_quotes.extend(quotes) else: while True: result = yf.screen(query, offset=offset, size=size) quotes = result.get("quotes", []) if not quotes: break all_quotes.extend(quotes) offset += size quotes_df = pd.DataFrame(all_quotes) symbols = [quote.get("symbol") for quote in all_quotes if quote.get("symbol")] historical_data = {} for batch_symbols in chunk_list(symbols, max_tickers_per_request): tickers_str = " ".join(batch_symbols) data = yf.download(tickers=tickers_str, start=start_date, end=end_date, interval="1d", group_by='ticker') if isinstance(data.columns, pd.MultiIndex): available_tickers = data.columns.get_level_values(0).unique().tolist() for ticker in batch_symbols: if ticker in available_tickers: historical_data[ticker] = data[ticker] else: ticker = batch_symbols[0] historical_data[ticker] = data time.sleep(delay_t) return quotes_df, historical_data
def update_stock_database(quotes_df, historical_data, upsert=False): session = Session() stock_quote_mappings = [] for idx, row in quotes_df.iterrows(): ticker = row.get("symbol") if not ticker: continue mapping = { "ticker": ticker, "asset_type": "STOCK", "symbol": ticker, "name": row.get("longName") or row.get("displayName") or ticker, "language": row.get("language"), "region": row.get("region"), "quote_type": row.get("quoteType"), "exchange": row.get("exchange"), "full_exchange_name": row.get("fullExchangeName"), "first_trade_date": safe_convert(row.get("firstTradeDateMilliseconds"), lambda x: datetime.datetime.fromtimestamp(x / 1000).date()), } stock_quote_mappings.append(mapping) if upsert: for mapping in stock_quote_mappings: session.merge(StockQuote(**mapping)) session.commit() else: session.bulk_insert_mappings(StockQuote, stock_quote_mappings) session.commit() stock_price_mappings = [] for ticker, df in historical_data.items(): if df is None or df.empty: continue for date, data_row in df.iterrows(): price_date = date.date() if isinstance(date, datetime.datetime) else date mapping = { "ticker": ticker, "asset_type": "STOCK", "price_date": price_date, "open_price": safe_convert(data_row.get("Open"), float), "high_price": safe_convert(data_row.get("High"), float), "low_price": safe_convert(data_row.get("Low"), float), "close_price": safe_convert(data_row.get("Close"), float), "volume": safe_convert(data_row.get("Volume"), Decimal) } stock_price_mappings.append(mapping) if upsert: for mapping in stock_price_mappings: session.merge(AssetPrice(**mapping)) session.commit() else: session.bulk_insert_mappings(AssetPrice, stock_price_mappings) session.commit() session.close()
def full_sync_stocks(): logger.info("Starting Full Sync for Stocks...") import yfinance as yf query_th = yf.EquityQuery("eq", ["region", "th"]) quotes_df_th, historical_data_th = fetch_yf_data(MAX_TICKERS_PER_REQUEST, REQUEST_DELAY_SECONDS, query_th, start_date=HISTORICAL_START_DATE) query_us = yf.EquityQuery("is-in", ["exchange", "NMS", "NYQ"]) quotes_df_us, historical_data_us = fetch_yf_data(MAX_TICKERS_PER_REQUEST, REQUEST_DELAY_SECONDS, query_us, start_date=HISTORICAL_START_DATE) quotes_df = pd.concat([quotes_df_th, quotes_df_us], ignore_index=True) historical_data = {**historical_data_th, **historical_data_us} update_stock_database(quotes_df, historical_data, upsert=False) session = Session() state = session.query(DeltaSyncState).filter_by(id=1).first() if not state: state = DeltaSyncState(id=1) state.last_full_sync = datetime.datetime.now() session.merge(state) session.commit() session.close() logger.info("Full Sync for Stocks Completed.")
def delta_sync_stocks(): logger.info("Starting Delta Sync for Stocks...") session = Session() state = session.query(DeltaSyncState).filter_by(id=1).first() session.close() today = datetime.datetime.now().date() two_days_ago = today - datetime.timedelta(days=2) import yfinance as yf query_th = yf.EquityQuery("eq", ["region", "th"]) quotes_df_th, historical_data_th = fetch_yf_data(MAX_TICKERS_PER_REQUEST, REQUEST_DELAY_SECONDS, query_th, start_date=two_days_ago.strftime("%Y-%m-%d"), end_date=today.strftime("%Y-%m-%d")) query_us = yf.EquityQuery("is-in", ["exchange", "NMS", "NYQ"]) quotes_df_us, historical_data_us = fetch_yf_data(MAX_TICKERS_PER_REQUEST, REQUEST_DELAY_SECONDS, query_us, start_date=two_days_ago.strftime("%Y-%m-%d"), end_date=today.strftime("%Y-%m-%d")) quotes_df = pd.concat([quotes_df_th, quotes_df_us], ignore_index=True) historical_data = {**historical_data_th, **historical_data_us} update_stock_database(quotes_df, historical_data, upsert=True) session = Session() state = session.query(DeltaSyncState).filter_by(id=1).first() if not state: state = DeltaSyncState(id=1) state.last_delta_sync = datetime.datetime.now() session.merge(state) session.commit() session.close() logger.info("Delta Sync for Stocks Completed.")
def full_sync_crypto(): logger.info("Starting Full Sync for Cryptocurrencies...") crypto_data = fetch_coingecko_data() historical_data = {} for coin in crypto_data: coin_id = coin.get("id") coin_symbol = coin.get("symbol").upper() + "USDT" df = fetch_binance_crypto_data(coin_symbol, HISTORICAL_START_DATE, None) historical_data[coin_id] = df time.sleep(REQUEST_DELAY_SECONDS) update_crypto_database(crypto_data, historical_data, upsert=False) session = Session() state = session.query(DeltaSyncState).filter_by(id=1).first() if not state: state = DeltaSyncState(id=1) state.last_full_sync = datetime.datetime.now() session.merge(state) session.commit() session.close() logger.info("Full Sync for Cryptocurrencies Completed.")
def delta_sync_crypto(): logger.info("Starting Delta Sync for Cryptocurrencies...") session = Session() state = session.query(DeltaSyncState).filter_by(id=1).first() session.close() today = datetime.datetime.now().date() two_days_ago = today - datetime.timedelta(days=2) crypto_data = fetch_coingecko_data() historical_data = {} for coin in crypto_data: coin_id = coin.get("id") coin_symbol = coin.get("symbol").upper() + "USDT" df = fetch_binance_crypto_data(coin_symbol, two_days_ago.strftime("%Y-%m-%d"), today.strftime("%Y-%m-%d")) historical_data[coin_id] = df time.sleep(REQUEST_DELAY_SECONDS) update_crypto_database(crypto_data, historical_data, upsert=True) session = Session() state = session.query(DeltaSyncState).filter_by(id=1).first() if not state: state = DeltaSyncState(id=1) state.last_delta_sync = datetime.datetime.now() session.merge(state) session.commit() session.close() logger.info("Delta Sync for Cryptocurrencies Completed.")
---------------------------
Data Source Classes
---------------------------
class StockDataSource: @staticmethod def get_latest_price(ticker): try: import yfinance as yf data = yf.Ticker(ticker) return data.fast_info["last_price"] except KeyError: return "NOT_FOUND" except Exception as e: logger.error(f"Error fetching latest price for stock {ticker}: {e}") return None
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
class CryptoDataSource: BASE_URL = "https://api.coingecko.com/api/v3"
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
---------------------------
Unified Latest Price and Cache Refresh
---------------------------
def get_latest_price(ticker, asset_type="STOCK"): key = (asset_type.upper(), ticker) query_counter[key] += 1 now = datetime.datetime.now() if key in latest_cache: value, timestamp = latest_cache[key] if value == "NOT_FOUND" and (now - timestamp).total_seconds() / 60 < NOT_FOUND_TTL: return "NOT_FOUND" elif value is not None and (now - timestamp).total_seconds() / 60 < REGULAR_TTL: return value if asset_type.upper() == "STOCK": price = StockDataSource.get_latest_price(ticker) elif asset_type.upper() == "CRYPTO": price = CryptoDataSource.get_latest_price(ticker) elif asset_type.upper() == "CURRENCY": price = CurrencyDataSource.get_latest_price(ticker) else: price = None if price == "NOT_FOUND": latest_cache[key] = ("NOT_FOUND", now) return "NOT_FOUND" elif price is not None: latest_cache[key] = (price, now) return price return "FETCH_ERROR"
def refresh_stock_top_n_tickers(): top_tickers = [ticker for (atype, ticker), _ in query_counter.most_common(TOP_N_TICKERS) if atype == "STOCK"] for batch in chunk_list(top_tickers, MAX_TICKERS_PER_REQUEST): prices = StockDataSource.refresh_latest_prices(batch) now = datetime.datetime.now() for ticker, price in prices.items(): latest_cache[("STOCK", ticker)] = (price, now) time.sleep(REQUEST_DELAY_SECONDS)
def refresh_crypto_prices(): prices = CryptoDataSource.get_all_latest_prices() now = datetime.datetime.now() for ticker, price in prices.items(): latest_cache[("CRYPTO", ticker)] = (price, now)
def refresh_all_latest_prices(): refresh_stock_top_n_tickers() refresh_crypto_prices() global last_cache_refresh last_cache_refresh = datetime.datetime.now()
def load_query_counter(): session = Session() query_counts = session.query(QueryCount).all() for qc in query_counts: key = (qc.ticker, qc.asset_type) query_counter[key] = qc.count last_saved_counts[key] = qc.count session.close()
def save_query_counter(): session = Session() for (ticker, asset_type), current_count in query_counter.items(): key = (ticker, asset_type) baseline = last_saved_counts.get(key, 0) delta = current_count - baseline if delta > 0: existing = session.query(QueryCount).filter_by(ticker=ticker, asset_type=asset_type).first() if existing: existing.count += delta else: session.add(QueryCount(ticker=ticker, asset_type=asset_type, count=current_count)) last_saved_counts[key] = current_count session.commit() session.close()
---------------------------
Flask Application and Endpoints
---------------------------
app = Flask(name) api_stats = Counter()
@app.route("/api/unified") def get_unified_ticker(): ticker = request.args.get("ticker") asset_type = request.args.get("asset_type", "STOCK").upper() if not ticker: return jsonify({"error": "Ticker parameter is required"}), 400 session = Session() if asset_type == "CRYPTO": quote = session.query(CryptoQuote).filter_by(ticker=ticker, asset_type=asset_type).first() elif asset_type == "CURRENCY": quote = session.query(CurrencyQuote).filter_by(ticker=ticker, asset_type=asset_type).first() else: quote = session.query(StockQuote).filter_by(ticker=ticker, asset_type=asset_type).first() prices = session.query(AssetPrice).filter_by(ticker=ticker, asset_type=asset_type).all() session.close() if not quote: return jsonify({"error": "Ticker not found"}), 404 quote_data = { "ticker": quote.ticker, "asset_type": asset_type, "symbol": quote.symbol, "name": quote.name } if asset_type == "STOCK": quote_data.update({ "language": quote.language, "region": quote.region, "quote_type": quote.quote_type, "exchange": quote.exchange, "full_exchange_name": quote.full_exchange_name, "first_trade_date": quote.first_trade_date.strftime("%Y-%m-%d") if quote.first_trade_date else None, }) elif asset_type == "CRYPTO": quote_data.update({ "image": quote.image, "ath": float(quote.ath) if quote.ath is not None else None, "ath_date": quote.ath_date.isoformat() if quote.ath_date else None, "atl": float(quote.atl) if quote.atl is not None else None, "atl_date": quote.atl_date.isoformat() if quote.atl_date else None, "total_supply": quote.total_supply, "max_supply": quote.max_supply, }) # For CURRENCY we only have ticker, symbol and name (plus new currency fields) key = (asset_type, ticker) cache_entry = latest_cache.get(key, (None, None)) latest_cache_data = { "price": cache_entry[0], "timestamp": cache_entry[1].isoformat() if cache_entry[1] else None } unified_data = { "ticker": ticker, "asset_type": asset_type, "quote_data": quote_data, "latest_cache": latest_cache_data, "historical_data": [ { "date": price.price_date.strftime("%Y-%m-%d"), "open": float(price.open_price) if price.open_price is not None else None, "high": float(price.high_price) if price.high_price is not None else None, "low": float(price.low_price) if price.low_price is not None else None, "close": float(price.close_price) if price.close_price is not None else None, "volume": float(price.volume) if price.volume is not None else None, } for price in prices ] } return jsonify(unified_data)
@app.route("/api/data_quality") def data_quality(): session = Session() total_stock_tickers = session.query(StockQuote).count() total_crypto_tickers = session.query(CryptoQuote).count() total_currency_tickers = session.query(CurrencyQuote).count() missing_long_name_stock = session.query(StockQuote).filter(StockQuote.name.is_(None)).count() missing_exchange_stock = session.query(StockQuote).filter(StockQuote.exchange.is_(None)).count() duplicate_entries = 0 duplicates = session.query( AssetPrice.ticker, AssetPrice.asset_type, func.count(AssetPrice.ticker).label("dup_count") ).group_by(AssetPrice.ticker, AssetPrice.asset_type).having(func.count(AssetPrice.ticker) > 1).all() for dup in duplicates: duplicate_entries += dup.dup_count - 1 session.close() data_quality_metrics = { "total_stock_tickers": total_stock_tickers, "total_crypto_tickers": total_crypto_tickers, "total_currency_tickers": total_currency_tickers, "missing_fields": missing_long_name_stock + missing_exchange_stock, "duplicates": duplicate_entries } return jsonify(data_quality_metrics)
@app.route("/api/ticker_traffic") def ticker_traffic(): data = [{"ticker": t[1], "asset_type": t[0], "count": count} for t, count in query_counter.most_common()] return jsonify(data)
@app.route("/api/cache_info") def cache_info(): global last_cache_refresh cache_job = scheduler.get_job("cache_refresh") if cache_job and cache_job.next_run_time: now_aware = datetime.datetime.now(tz=cache_job.next_run_time.tzinfo) diff_seconds = (cache_job.next_run_time - now_aware).total_seconds() next_cache_refresh = f"{int(diff_seconds // 60)} minutes" if diff_seconds >= 60 else f"{int(diff_seconds)} seconds" else: next_cache_refresh = "N/A" return jsonify({ "last_cache_refresh": last_cache_refresh.isoformat() if last_cache_refresh else None, "next_cache_refresh": next_cache_refresh })
@app.before_request def before_request(): if request.path.startswith('/api/'): key = request.path + "" + request.args.get("ticker", "") + "" + request.args.get("asset_type", "STOCK").upper() api_stats[key] += 1
@app.route("/api/latest") def get_latest(): ticker = request.args.get("ticker") asset_type = request.args.get("asset_type", "STOCK").upper() if not ticker: return jsonify({"error": "Ticker parameter is required"}), 400 result = get_latest_price(ticker, asset_type) key = (asset_type, ticker) timestamp = latest_cache.get(key, (None, datetime.datetime.now()))[1] if isinstance(result, (int, float)): return jsonify({ "ticker": ticker, "asset_type": asset_type, "price": result, "timestamp": timestamp.isoformat() }) elif result == "NOT_FOUND": return jsonify({"error": "Ticker not found"}), 404 else: return jsonify({"error": "Unable to fetch latest price"}), 500
@app.route("/api/assets") def get_assets(): asset_type = request.args.get("asset_type", "STOCK").upper() session = Session() if asset_type == "CRYPTO": quotes = session.query(CryptoQuote).all() elif asset_type == "CURRENCY": quotes = session.query(CurrencyQuote).all() else: quotes = session.query(StockQuote).all() session.close() assets = [] for quote in quotes: key = (asset_type, quote.ticker) latest = latest_cache.get(key, (None, None)) assets.append({ "ticker": quote.ticker, "asset_type": asset_type, "name": quote.name, "symbol": quote.symbol, "latest_price": latest[0], "updated_at": latest[1].isoformat() if latest[1] else None }) return jsonify(assets)
@app.route("/api/historical") def get_historical(): ticker = request.args.get("ticker") asset_type = request.args.get("asset_type", "STOCK").upper() if not ticker: return jsonify({"error": "Ticker parameter is required"}), 400 session = Session() prices = session.query(AssetPrice).filter_by(ticker=ticker, asset_type=asset_type).all() session.close() if not prices: return jsonify({"error": "No historical data found for ticker"}), 404 data = [] for price in prices: record = { "date": price.price_date.strftime("%Y-%m-%d"), "open": float(price.open_price) if price.open_price is not None else None, "high": float(price.high_price) if price.high_price is not None else None, "low": float(price.low_price) if price.low_price is not None else None, "close": float(price.close_price) if price.close_price is not None else None, "volume": float(price.volume) if price.volume is not None else None, } data.append(record) return jsonify({"ticker": ticker, "asset_type": asset_type, "historical_data": data})
@app.route("/api/stats") def get_stats(): session = Session() total_stock_tickers = session.query(StockQuote).count() total_crypto_tickers = session.query(CryptoQuote).count() total_currency_tickers = session.query(CurrencyQuote).count() stock_prices_count = session.query(AssetPrice).filter_by(asset_type="STOCK").count() crypto_prices_count = session.query(AssetPrice).filter_by(asset_type="CRYPTO").count() currency_prices_count = session.query(AssetPrice).filter_by(asset_type="CURRENCY").count() delta_sync_state_count = session.query(DeltaSyncState).count() query_counts_count = session.query(QueryCount).count() region_counts = session.query(StockQuote.region, func.count(StockQuote.ticker)).group_by(StockQuote.region).all() state = session.query(DeltaSyncState).filter_by(id=1).first() session.close() total = sum(count for _, count in region_counts) region_distribution = {region: {"count": count, "percentage": (count / total * 100) if total > 0 else 0} for region, count in region_counts} last_full_sync = state.last_full_sync.isoformat() if state and state.last_full_sync else None last_delta_sync = state.last_delta_sync.isoformat() if state and state.last_delta_sync else None db_file = os.path.join('instance', 'stock_data.db') if os.path.exists(db_file): db_size = os.path.getsize(db_file) / (1024 * 1024) db_size_str = f"{db_size:.2f} MB" if db_size < 1024 else f"{db_size / 1024:.2f} GB" else: db_size_str = "Database file not found" stats = { "total_stock_tickers": total_stock_tickers, "total_crypto_tickers": total_crypto_tickers, "total_currency_tickers": total_currency_tickers, "db_size": db_size_str, "cache_hit_rate": "100%", "api_requests_24h": sum(api_stats.values()), "table_records": { "stock_quotes": total_stock_tickers, "crypto_quotes": total_crypto_tickers, "currency_quotes": total_currency_tickers, "asset_prices_stock": stock_prices_count, "asset_prices_crypto": crypto_prices_count, "asset_prices_currency": currency_prices_count, "delta_sync_state": delta_sync_state_count, "query_counts": query_counts_count }, "region_distribution": region_distribution, "last_full_sync": last_full_sync, "last_delta_sync": last_delta_sync, "cache_size": len(latest_cache), "api_stats": dict(api_stats) } return jsonify(stats)
@app.route("/api/tickers") def get_tickers(): query = request.args.get("query", "").strip().lower() if not query: return jsonify({"error": "Query parameter is required"}), 400
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
    if asset_type == "CRYPTO":
        base_query = session.query(CryptoQuote).filter(
            (CryptoQuote.ticker.ilike(f"%{query}%")) |
            (CryptoQuote.name.ilike(f"%{query}%")) |
            (CryptoQuote.symbol.ilike(f"%{query}%"))
        )
    elif asset_type == "CURRENCY":
        base_query = session.query(CurrencyQuote).filter(
            (CurrencyQuote.ticker.ilike(f"%{query}%")) |
            (CurrencyQuote.name.ilike(f"%{query}%")) |
            (CurrencyQuote.symbol.ilike(f"%{query}%"))
        )
    else:
        base_query = session.query(StockQuote).filter(
            (StockQuote.ticker.ilike(f"%{query}%")) |
            (StockQuote.name.ilike(f"%{query}%")) |
            (StockQuote.symbol.ilike(f"%{query}%"))
        )

    if fuzzy_enabled:
        candidate_results = base_query.limit(50).all()
        scored_results = []
        for record in candidate_results:
            score = max(
                fuzz.token_set_ratio(query, record.ticker.lower()),
                fuzz.token_set_ratio(query, record.name.lower()),
                fuzz.token_set_ratio(query, record.symbol.lower())
            )
            scored_results.append((score, record))
        scored_results.sort(key=lambda x: x[0], reverse=True)
        final_results = [record for _, record in scored_results[offset: offset + limit]]
    else:
        final_results = base_query.offset(offset).limit(limit).all()

    session.close()
    response = [
        {"ticker": r.ticker, "name": r.name, "symbol": r.symbol}
        for r in final_results
    ]
    return jsonify(response)

except SQLAlchemyError as e:
    current_app.logger.error(f"Database error in get_tickers: {e}")
    return jsonify({"error": "Internal server error"}), 500
except Exception as e:
    current_app.logger.error(f"Unexpected error in get_tickers: {e}")
    return jsonify({"error": "Internal server error"}), 500
@app.route("/api/sync/full", methods=["POST"]) def sync_full(): data = request.get_json() or {} ticker = data.get("ticker") asset_type = data.get("asset_type", "STOCK").upper() try: if ticker: if asset_type == "STOCK": quotes_df, historical_data = fetch_yf_data_for_ticker(ticker) if quotes_df is not None and historical_data is not None: update_stock_database(quotes_df, historical_data, upsert=True) return jsonify({"message": f"Full sync for stock ticker {ticker} completed."}) else: return jsonify({"error": f"Failed to fetch data for stock ticker {ticker}"}), 404 elif asset_type == "CRYPTO": coin_data = fetch_coingecko_data_for_ticker(ticker) if coin_data: symbol = coin_data["symbol"].upper() + "USDT" historical_data = fetch_binance_crypto_data(symbol, HISTORICAL_START_DATE, None) if historical_data is not None: update_crypto_database([coin_data], {ticker: historical_data}, upsert=True) return jsonify({"message": f"Full sync for crypto ticker {ticker} completed."}) else: return jsonify({"error": f"Failed to fetch historical data for crypto ticker {ticker}"}), 404 else: return jsonify({"error": f"Failed to fetch metadata for crypto ticker {ticker}"}), 404 elif asset_type == "CURRENCY": currency_item = None currency_list = download_currency_list() for item in currency_list: if item["ticker"].lower() == ticker.lower(): currency_item = item break if currency_item: df = fetch_alpha_fx_daily("USD", currency_item["ticker"], HISTORICAL_START_DATE, None, outputsize="full") update_currency_database([currency_item], {currency_item["ticker"]: df}, upsert=True) return jsonify({"message": f"Full sync for currency ticker {ticker} completed."}) else: return jsonify({"error": f"Failed to fetch data for currency ticker {ticker}"}), 404 else: return jsonify({"error": "Invalid asset_type"}), 400 else: if asset_type == "CRYPTO": full_sync_crypto() return jsonify({"message": "Global full sync for cryptocurrencies completed."}) elif asset_type == "CURRENCY": full_sync_currency() return jsonify({"message": "Global full sync for currencies completed."}) else: full_sync_stocks() return jsonify({"message": "Global full sync for stocks completed."}) except Exception as e: logger.error(f"Error in full sync: {e}") return jsonify({"error": str(e)}), 500
@app.route("/api/sync/delta", methods=["POST"]) def sync_delta(): data = request.get_json() or {} ticker = data.get("ticker") asset_type = data.get("asset_type", "STOCK").upper() try: if ticker: today = datetime.datetime.now().date() two_days_ago = today - datetime.timedelta(days=2) if asset_type == "STOCK": quotes_df, historical_data = fetch_yf_data_for_ticker(ticker, start_date=two_days_ago.strftime("%Y-%m-%d"), end_date=today.strftime("%Y-%m-%d")) if quotes_df is not None and historical_data is not None: update_stock_database(quotes_df, historical_data, upsert=True) return jsonify({"message": f"Delta sync for stock ticker {ticker} completed."}) else: return jsonify({"error": f"Failed to fetch delta data for stock ticker {ticker}"}), 404 elif asset_type == "CRYPTO": coin_data = fetch_coingecko_data_for_ticker(ticker) if coin_data: symbol = coin_data["symbol"].upper() + "USDT" historical_data = fetch_binance_crypto_data(symbol, two_days_ago.strftime("%Y-%m-%d"), today.strftime("%Y-%m-%d")) if historical_data is not None: update_crypto_database([coin_data], {ticker: historical_data}, upsert=True) return jsonify({"message": f"Delta sync for crypto ticker {ticker} completed."}) else: return jsonify({"error": f"Failed to fetch delta historical data for crypto ticker {ticker}"}), 404 else: return jsonify({"error": f"Failed to fetch metadata for crypto ticker {ticker}"}), 404 elif asset_type == "CURRENCY": currency_item = None currency_list = download_currency_list() for item in currency_list: if item["ticker"].lower() == ticker.lower(): currency_item = item break if currency_item: today = datetime.datetime.now().date() two_days_ago = today - datetime.timedelta(days=2) df = fetch_alpha_fx_daily("USD", currency_item["ticker"], two_days_ago.strftime("%Y-%m-%d"), today.strftime("%Y-%m-%d"), outputsize="compact") update_currency_database([currency_item], {currency_item["ticker"]: df}, upsert=True) return jsonify({"message": f"Delta sync for currency ticker {ticker} completed."}) else: return jsonify({"error": f"Failed to fetch data for currency ticker {ticker}"}), 404 else: return jsonify({"error": "Invalid asset_type"}), 400 else: if asset_type == "CRYPTO": delta_sync_crypto() return jsonify({"message": "Global delta sync for cryptocurrencies completed."}) elif asset_type == "CURRENCY": delta_sync_currency() return jsonify({"message": "Global delta sync for currencies completed."}) else: delta_sync_stocks() return jsonify({"message": "Global delta sync for stocks completed."}) except Exception as e: logger.error(f"Error in delta sync: {e}") return jsonify({"error": str(e)}), 500
@app.route("/dashboard") def dashboard(): return render_template('dashboard.html')
---------------------------
Scheduler Setup
---------------------------
scheduler = BackgroundScheduler() scheduler.add_job(refresh_all_latest_prices, "interval", minutes=LATEST_CACHE_REFRESH_INTERVAL_MINUTES, id="cache_refresh") scheduler.add_job(delta_sync_stocks, "interval", days=DELTA_SYNC_INTERVAL_DAYS, id="delta_sync_stocks") scheduler.add_job(delta_sync_crypto, "interval", days=DELTA_SYNC_INTERVAL_DAYS, id="delta_sync_crypto") scheduler.add_job(delta_sync_currency, "interval", days=DELTA_SYNC_INTERVAL_DAYS, id="delta_sync_currency") scheduler.add_job(save_query_counter, "interval", minutes=QUERY_COUNTER_SAVE_INTERVAL_MINUTES, id="save_query_counter") scheduler.add_job(refresh_currency_prices, "interval", minutes=60, id="currency_cache_refresh") scheduler.start()
load_query_counter()
if name == "main": session = Session() stock_quotes_count = session.query(StockQuote).count() crypto_quotes_count = session.query(CryptoQuote).count() currency_quotes_count = session.query(CurrencyQuote).count() session.close() if stock_quotes_count == 0 or crypto_quotes_count == 0 or currency_quotes_count == 0: Base.metadata.drop_all(engine) Base.metadata.create_all(engine) refresh_all_latest_prices() app.run(host=FLASK_HOST, port=FLASK_PORT)
--- End of app.py ---
1.quote_currency should be mapping to Asset (currency) 2.for currency data fetch please also update from currency to be from our asset example THB / USD is fetching from = THB , to = USD to be align with new design.

give full updated file.
