
# Price Provider Service

## Overview

The Price Provider Service is a Python-based application that retrieves stock quotes and historical price data from [yfinance](https://pypi.org/project/yfinance/). It supports:

- **Full Sync:** Populates the database with historical data starting from January 1, 2020, including static quote (metadata) information.
- **Delta Sync:** Updates the database daily with the latest two days of data, ensuring up-to-date pricing and quote changes.
- **Latest Price Cache:** Maintains an in-memory cache refreshed every 5 minutes to serve the most recent price data without exceeding rate limits.
- **RESTful API:** Exposes endpoints to fetch:
  - The latest price for a specified ticker.
  - A list of all tickers and their metadata by asset type (e.g., "us" or "th").
  - Historical data for a given ticker along with computed statistics (e.g., average volume).

## Architecture

The service is composed of the following key components:

- **Data Ingestion Jobs:**
  - **Full Sync Job:** Runs on startup (if the database is empty) to fetch and store all historical data from the start date.
  - **Delta Sync Job:** Scheduled to run daily to update the latest two days of data.
- **Database:**  
  - Uses SQLite (by default) to store static stock quotes (metadata) and dynamic historical price data.
- **In-Memory Cache:**  
  - Latest price data is stored in a cache that is refreshed every 5 minutes to minimize external API calls.
- **API Layer:**  
  - A Flask-based REST API exposes endpoints for querying the latest price, asset metadata, and historical data.
- **Scheduler:**  
  - APScheduler is used to schedule the Delta Sync and cache refresh jobs.

## Installation

### Prerequisites

- Python 3.7 or later
- `pip` package manager

### Install Dependencies

Install the required packages using:

```bash
pip install flask sqlalchemy yfinance apscheduler pandas
```

## Configuration

All adjustable parameters are centralized at the top of the service code. Key parameters include:

- **Data Fetching Parameters:**
  - `MAX_TICKERS_PER_REQUEST`: Maximum tickers per batch request.
  - `REQUEST_DELAY_SECONDS`: Delay between batch requests (in seconds).
  - `HISTORICAL_START_DATE`: Start date for fetching historical data.
  - `YFINANCE_REGION`: Region used in the query (e.g., "us" or "th").
- **Database Configuration:**
  - `DATABASE_URL`: Database connection string (default uses SQLite).
- **API Server Configuration:**
  - `FLASK_HOST` and `FLASK_PORT`: Host and port for the Flask API.
- **Scheduler Intervals:**
  - `LATEST_CACHE_REFRESH_INTERVAL_MINUTES`: Interval for refreshing the in-memory latest price cache.
  - `DELTA_SYNC_INTERVAL_DAYS`: Interval for running the Delta Sync job.

## Running the Service

To start the service, run the main script:

```bash
python service.py
```

- **Full Sync:**  
  If the database is empty, the service triggers a full sync to populate historical data from January 1, 2020.
- **Scheduled Jobs:**  
  APScheduler automatically handles the Delta Sync (daily) and the latest cache refresh (every 5 minutes).
- **API Server:**  
  The Flask API starts and listens on the configured host and port (default: `http://0.0.0.0:5000`).

## API Documentation

### 1. Get Latest Price

**Endpoint:**  
```
GET /api/latest
```

**Description:**  
Returns the most recent cached price for a specified stock ticker.

**Query Parameter:**  
- `ticker` (required): The stock ticker symbol.

**Example Request:**  
```
GET http://localhost:5000/api/latest?ticker=AAPL
```

**Example Response:**
```json
{
  "AAPL": 214.0
}
```

### 2. Get Assets Metadata

**Endpoint:**  
```
GET /api/assets
```

**Description:**  
Lists all tickers and their static metadata (e.g., company name, exchange, region) filtered by asset type.

**Query Parameter:**  
- `type` (required): The asset type/region (e.g., "us" or "th").

**Example Request:**  
```
GET http://localhost:5000/api/assets?type=us
```

**Example Response:**
```json
[
  {
    "ticker": "AAPL",
    "long_name": "Apple Inc.",
    "short_name": "Apple",
    "region": "us",
    "exchange": "NASDAQ"
  },
  {
    "ticker": "MSFT",
    "long_name": "Microsoft Corporation",
    "short_name": "Microsoft",
    "region": "us",
    "exchange": "NASDAQ"
  }
]
```

### 3. Get Historical Data

**Endpoint:**  
```
GET /api/historical
```

**Description:**  
Retrieves historical price data for a given ticker along with computed metrics (e.g., average volume).

**Query Parameter:**  
- `ticker` (required): The stock ticker symbol.

**Example Request:**  
```
GET http://localhost:5000/api/historical?ticker=AAPL
```

**Example Response:**
```json
{
  "ticker": "AAPL",
  "historical_data": [
    {
      "date": "2020-01-02",
      "open": 75.0,
      "high": 77.0,
      "low": 74.0,
      "close": 76.0,
      "volume": 1000000
    },
    {
      "date": "2020-01-03",
      "open": 76.0,
      "high": 78.0,
      "low": 75.0,
      "close": 77.0,
      "volume": 1100000
    }
    // ... additional records
  ],
  "average_volume": 1050000
}
```

## Project Structure

```
.
├── README.md         # This file
├── service.py        # Main service code (contains API endpoints, sync jobs, configuration)
└── requirements.txt  # (Optional) List of dependencies
```

## License

This project is provided "as-is" without any warranties. Use it at your own risk.

## Acknowledgments

- [yfinance](https://pypi.org/project/yfinance/) for fetching stock data.
- [Flask](https://flask.palletsprojects.com/) for the API framework.
- [SQLAlchemy](https://www.sqlalchemy.org/) for database ORM.
- [APScheduler](https://apscheduler.readthedocs.io/) for scheduling background jobs.

