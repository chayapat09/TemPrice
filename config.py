import os
import datetime
import logging

# Configurable Parameters
MAX_TICKERS_PER_REQUEST = 50
REQUEST_DELAY_SECONDS = 5
HISTORICAL_START_DATE = "2020-01-01"
DATABASE_URL = "sqlite:///instance/stock_data.db"
FLASK_HOST = "0.0.0.0"
FLASK_PORT = 8082
TOP_N_TICKERS = 100
LATEST_CACHE_REFRESH_INTERVAL_MINUTES = 1
REGULAR_TTL = 15            # in minutes
NOT_FOUND_TTL = 1440        # in minutes
QUERY_COUNTER_SAVE_INTERVAL_MINUTES = 5
DELTA_SYNC_INTERVAL_DAYS = 1

# Ensure the 'instance' directory exists
if not os.path.exists('instance'):
    os.makedirs('instance')

# Logging Configuration
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)