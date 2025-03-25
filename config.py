import os
import datetime
import logging

# Configurable Parameters
MAX_TICKERS_PER_REQUEST = 15
REQUEST_DELAY_SECONDS = 5
HISTORICAL_START_DATE = "2013-01-01"
DATABASE_URL = "sqlite:///instance/stock_data.db"
FLASK_HOST = "0.0.0.0"
FLASK_PORT = 8082
TOP_N_TICKERS = 100
LATEST_CACHE_REFRESH_INTERVAL_MINUTES = 1
# New parameter for Currency realtime cache refresh interval (6 hours)
CURRENCY_CACHE_REFRESH_INTERVAL_MINUTES = 360
REGULAR_TTL = 15            # in minutes
NOT_FOUND_TTL = 1440        # in minutes
QUERY_COUNTER_SAVE_INTERVAL_MINUTES = 5
DELTA_SYNC_INTERVAL_DAYS = 1

# AlphaVantage API Key for Currency Data (replace with your own key)
ALPHAVANTAGE_API_KEY = "JVK9DJKA9HTU74LI"

# Ensure the 'instance' directory exists
if not os.path.exists('instance'):
    os.makedirs('instance')

# Logging Configuration
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)