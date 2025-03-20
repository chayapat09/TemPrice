import datetime
import logging
from sqlalchemy import BigInteger, Column, Date, DateTime, DECIMAL, Integer, String, create_engine, text
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker

# Logging Configuration
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# Database URL
DATABASE_URL = "sqlite:///instance/stock_data.db"

# Create engine
engine = create_engine(DATABASE_URL, echo=False)

# Define the new models
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
    total_supply = Column(BigInteger)    # Generally static once set
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
    volume = Column(BigInteger)

# Delta Sync State Model (unchanged between old and new schema)
class DeltaSyncState(Base):
    __tablename__ = "delta_sync_state"
    id = Column(Integer, primary_key=True)
    last_full_sync = Column(DateTime)
    last_delta_sync = Column(DateTime)

# Query Count Model with composite key
class QueryCount(Base):
    __tablename__ = "query_counts"
    ticker = Column(String(50), primary_key=True)
    asset_type = Column(String(10), primary_key=True)
    count = Column(Integer, default=0)

def migrate_database():
    """
    Migrates the database schema from the old model (A) to the new model (B) with data migration.
    """
    with engine.connect() as conn:
        # Step 1: Rename old tables to temporary names
        try:
            conn.execute(text("ALTER TABLE stock_quotes RENAME TO old_stock_quotes"))
            logger.info("Renamed stock_quotes to old_stock_quotes")
        except Exception as e:
            logger.info("Table stock_quotes not found or already renamed: %s", e)
        
        try:
            conn.execute(text("ALTER TABLE stock_prices RENAME TO old_stock_prices"))
            logger.info("Renamed stock_prices to old_stock_prices")
        except Exception as e:
            logger.info("Table stock_prices not found or already renamed: %s", e)
        
        try:
            conn.execute(text("ALTER TABLE query_counts RENAME TO old_query_counts"))
            logger.info("Renamed query_counts to old_query_counts")
        except Exception as e:
            logger.info("Table query_counts not found or already renamed: %s", e)
        
        # Step 2: Create new tables based on the updated models
        Base.metadata.create_all(engine)
        logger.info("Created new tables based on the new schema")
        
        # Step 3: Migrate data from old tables to new tables
        # Migrate stock_quotes to new stock_quotes
        if 'old_stock_quotes' in conn.dialect.get_table_names(conn):
            conn.execute(text("""
                INSERT INTO stock_quotes (
                    ticker, asset_type, symbol, name, language, region, quote_type,
                    exchange, full_exchange_name, first_trade_date
                )
                SELECT
                    ticker, 'STOCK', ticker, long_name, language, region, quote_type,
                    exchange, full_exchange_name, first_trade_date
                FROM old_stock_quotes
            """))
            logger.info("Migrated data from old_stock_quotes to stock_quotes")
            conn.execute(text("DROP TABLE old_stock_quotes"))
            logger.info("Dropped old_stock_quotes table")
        
        # Migrate stock_prices to asset_prices
        if 'old_stock_prices' in conn.dialect.get_table_names(conn):
            conn.execute(text("""
                INSERT INTO asset_prices (
                    ticker, asset_type, price_date, open_price, high_price,
                    low_price, close_price, volume
                )
                SELECT
                    ticker, 'STOCK', price_date, open_price, high_price,
                    low_price, close_price, volume
                FROM old_stock_prices
            """))
            logger.info("Migrated data from old_stock_prices to asset_prices")
            conn.execute(text("DROP TABLE old_stock_prices"))
            logger.info("Dropped old_stock_prices table")
        
        # Migrate query_counts to new query_counts
        if 'old_query_counts' in conn.dialect.get_table_names(conn):
            conn.execute(text("""
                INSERT INTO query_counts (ticker, asset_type, count)
                SELECT ticker, 'STOCK', count
                FROM old_query_counts
            """))
            logger.info("Migrated data from old_query_counts to query_counts")
            conn.execute(text("DROP TABLE old_query_counts"))
            logger.info("Dropped old_query_counts table")
        
        logger.info("Database migration completed successfully")

# Execute the migration
if __name__ == "__main__":
    migrate_database()