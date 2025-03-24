from sqlalchemy import BigInteger, Column, Date, DateTime, DECIMAL, Integer, String, ForeignKey, create_engine, and_, ForeignKeyConstraint
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker, relationship
from config import DATABASE_URL

Base = declarative_base()

class Asset(Base):
    __tablename__ = "assets"
    asset_type = Column(String(10), primary_key=True)  # e.g. STOCK, CRYPTO, CURRENCY
    symbol = Column(String(50), primary_key=True)
    name = Column(String(100))
    source_asset_key = Column(String(50))  # Key used for price queries
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
    __table_args__ = (
        ForeignKeyConstraint([asset_type, symbol], ["assets.asset_type", "assets.symbol"]),
    )
    __mapper_args__ = {
        'polymorphic_identity': 'CURRENCY',
        'inherit_condition': and_(asset_type == Asset.asset_type, symbol == Asset.symbol)
    }

class DataSource(Base):
    __tablename__ = "data_sources"
    id = Column(Integer, primary_key=True)
    name = Column(String(50), unique=True)
    description = Column(String(200), nullable=True)

class AssetQuote(Base):
    __tablename__ = "asset_quotes"
    id = Column(Integer, primary_key=True)
    from_asset_type = Column(String(10))
    from_asset_symbol = Column(String(50))
    to_asset_type = Column(String(10))
    to_asset_symbol = Column(String(50))
    data_source_id = Column(Integer, ForeignKey("data_sources.id"))
    ticker = Column(String(50))          # Composite ticker (e.g. TSLAUSD or BTCUSDT)
    source_ticker = Column(String(50))     # Ticker/key used for querying the data source
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

class DeltaSyncState(Base):
    __tablename__ = "delta_sync_state"
    id = Column(Integer, primary_key=True)
    last_full_sync = Column(DateTime)
    last_delta_sync = Column(DateTime)

class QueryCount(Base):
    __tablename__ = "query_counts"
    ticker = Column(String(50), primary_key=True)  # Composite ticker from AssetQuote
    asset_type = Column(String(10), primary_key=True)
    count = Column(Integer, default=0)

# --- Updated Derived Ticker Model ---
class DerivedTicker(Base):
    __tablename__ = "derived_tickers"
    ticker = Column(String(50), primary_key=True)  # Unique derived ticker identifier (renamed from "name")
    formula = Column(String(255), nullable=False)

engine = create_engine(DATABASE_URL, echo=False)
Base.metadata.create_all(engine)
Session = sessionmaker(bind=engine)
