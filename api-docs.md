# Price Provider Service API Documentation

**Base URL:**  
Assuming the service is running locally, the base URL is:  
```
http://localhost:5000
```

---

## Endpoints

### 1. Get Latest Price

**Endpoint:**  
```
GET /api/latest
```

**Description:**  
Returns the most recent cached price for the specified stock ticker. The latest price is fetched from an in-memory cache that is refreshed every 5 minutes to reduce calls to the data source.

**Query Parameters:**  
- **ticker** (required, string): The stock ticker symbol for which the latest price is requested.

**Responses:**

- **Success (200):**  
  Returns a JSON object with the ticker symbol as the key and its latest price as the value.  
  **Example Response:**
  ```json
  {
    "AAPL": 214.0
  }
  ```

- **Error (400):**  
  If the ticker parameter is missing.
  ```json
  {
    "error": "Ticker parameter is required"
  }
  ```

- **Error (404):**  
  If the ticker is not found in the latest cache.
  ```json
  {
    "error": "Ticker not found in latest cache"
  }
  ```

---

### 2. Get Assets Metadata

**Endpoint:**  
```
GET /api/assets
```

**Description:**  
Lists all tickers and their static metadata (such as company names, exchange, region, etc.) filtered by the asset type. The asset type corresponds to the region (e.g., "us" or "th").

**Query Parameters:**  
- **type** (required, string): The asset type/region (for example, `us` for U.S. stocks or `th` for Thailand stocks).

**Responses:**

- **Success (200):**  
  Returns a JSON array of asset objects, each containing metadata fields.  
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

- **Error (400):**  
  If the asset type parameter is missing.
  ```json
  {
    "error": "Asset type parameter is required"
  }
  ```

---

### 3. Get Historical Data

**Endpoint:**  
```
GET /api/historical
```

**Description:**  
Retrieves the historical price data for a specified ticker along with computed metrics (e.g., average volume) based on the data stored in the database.

**Query Parameters:**  
- **ticker** (required, string): The stock ticker symbol for which historical price data is requested.

**Responses:**

- **Success (200):**  
  Returns a JSON object containing:
  - **ticker:** The ticker symbol.
  - **historical_data:** An array of records where each record includes the trading date, open, high, low, close prices, and volume.
  - **average_volume:** The average trading volume computed from the available historical data.  
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
      // ... more records
    ],
    "average_volume": 1050000
  }
  ```

- **Error (400):**  
  If the ticker parameter is missing.
  ```json
  {
    "error": "Ticker parameter is required"
  }
  ```

- **Error (404):**  
  If no historical data is found for the given ticker.
  ```json
  {
    "error": "No historical data found for ticker"
  }
  ```

---

## General Notes

- **Data Source:**  
  All price and quote data are fetched from yfinance. Historical data is synchronized using Full Sync (initial run) and Delta Sync (updates) jobs, and latest prices are served from an in-memory cache.

- **Rate Limiting:**  
  The service fetches data from the yfinance source at most once every 5 minutes for latest prices to avoid rate limits.

- **Data Refresh Jobs:**  
  - **Full Sync:** Runs on startup (if the database is empty) and populates all historical data from January 1, 2020.
  - **Delta Sync:** Runs at a scheduled interval (default once daily) to update the latest two days of data.
  - **Latest Cache Refresh:** Runs every 5 minutes to update the in-memory cache.

- **Response Format:**  
  All responses are in JSON format.

---

This documentation outlines the service endpoints, parameters, and expected responses for building clients against the Price Provider Service. Adjust parameters and deployment settings as needed for your environment.