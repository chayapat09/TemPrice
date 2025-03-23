# Stock and Crypto Data API Documentation

## Overview
This API provides access to both stock and cryptocurrency data, allowing clients to fetch unified ticker information, query historical prices, check data quality, monitor ticker traffic, and perform data synchronization. The API supports both GET and POST requests and offers detailed endpoints for various functionalities.

## Base URL
All API endpoints use the following base URL (adjust to your server configuration):
```
http://<server_address>:8082
```

## General Information
- All endpoints return data in **JSON** format.
- Dates and timestamps follow the **ISO 8601** standard (e.g., `2023-10-01T12:00:00`).
- The API does not require authentication.
- Be mindful of rate limits, especially for endpoints that trigger data synchronization or fetch real-time data.

---

## Endpoints

### 1. Get Unified Ticker Data
- **URL:** `/api/unified`
- **Method:** `GET`
- **Query Parameters:**
  - `ticker` (required, string): The ticker symbol (e.g., `AAPL` or `bitcoin`).
  - `asset_type` (optional, string, default: "STOCK"): Either "STOCK" or "CRYPTO".

**Description:**
Retrieves unified data for the specified ticker, including static quote data, the latest cached price, and historical price data.

**Responses:**
- `200 OK`: JSON object containing `ticker`, `asset_type`, `quote_data`, `latest_cache`, and `historical_data`.
- `400 Bad Request`: Missing `ticker` parameter.
- `404 Not Found`: Ticker not found in the database.

**Example Response:**
```json
{
  "ticker": "AAPL",
  "asset_type": "STOCK",
  "quote_data": {
    "ticker": "AAPL",
    "asset_type": "STOCK",
    "symbol": "AAPL",
    "name": "Apple Inc.",
    "language": "en-US",
    "region": "US",
    "quote_type": "EQUITY",
    "exchange": "NMS",
    "full_exchange_name": "NasdaqGS",
    "first_trade_date": "1980-12-12"
  },
  "latest_cache": {
    "price": 150.25,
    "timestamp": "2023-10-01T12:00:00"
  },
  "historical_data": [
    {
      "date": "2023-09-30",
      "open": 149.50,
      "high": 151.00,
      "low": 149.00,
      "close": 150.25,
      "volume": 1000000
    }
  ]
}
```

---

### 2. Get Data Quality Metrics
- **URL:** `/api/data_quality`
- **Method:** `GET`

**Description:**
Provides data quality metrics such as the total number of stock and crypto tickers, count of missing fields, and duplicate entries.

**Example Response:**
```json
{
  "total_stock_tickers": 5000,
  "total_crypto_tickers": 250,
  "missing_fields": 100,
  "duplicates": 0
}
```

---

### 3. Get Ticker Traffic
- **URL:** `/api/ticker_traffic`
- **Method:** `GET`

**Description:**
Returns query counts for each ticker and asset type, reflecting API usage frequency.

**Example Response:**
```json
[
  { "ticker": "AAPL", "asset_type": "STOCK", "count": 100 },
  { "ticker": "bitcoin", "asset_type": "CRYPTO", "count": 50 }
]
```

---

### 4. Get Cache Information
- **URL:** `/api/cache_info`
- **Method:** `GET`

**Description:**
Provides details about the cache including the last refresh time and the time until the next scheduled refresh.

**Example Response:**
```json
{
  "last_cache_refresh": "2023-10-01T12:00:00",
  "next_cache_refresh": "5 minutes"
}
```

---

### 5. Get Latest Price
- **URL:** `/api/latest`
- **Method:** `GET`
- **Query Parameters:**
  - `ticker` (required, string)
  - `asset_type` (optional, string, default: "STOCK")

**Description:**
Retrieves the latest price for the specified ticker from the cache or fetches it if necessary.

**Example Response:**
```json
{
  "ticker": "AAPL",
  "asset_type": "STOCK",
  "price": 150.25,
  "timestamp": "2023-10-01T12:00:00"
}
```

---

### 6. Get Assets
- **URL:** `/api/assets`
- **Method:** `GET`
- **Query Parameters:**
  - `asset_type` (optional, string, default: "STOCK")

**Description:**
Lists all available assets of the specified type with their latest prices and details.

**Example Response:**
```json
[
  {
    "ticker": "AAPL",
    "asset_type": "STOCK",
    "name": "Apple Inc.",
    "symbol": "AAPL",
    "latest_price": 150.25,
    "updated_at": "2023-10-01T12:00:00"
  }
]
```

---

### 7. Get Historical Data
- **URL:** `/api/historical`
- **Method:** `GET`
- **Query Parameters:**
  - `ticker` (required, string)
  - `asset_type` (optional, string, default: "STOCK")

**Description:**
Retrieves historical price data for the specified ticker.

**Example Response:**
```json
{
  "ticker": "AAPL",
  "asset_type": "STOCK",
  "historical_data": [
    {
      "date": "2023-09-30",
      "open": 149.50,
      "high": 151.00,
      "low": 149.00,
      "close": 150.25,
      "volume": 1000000
    }
  ]
}
```

---

### 8. Get Statistics
- **URL:** `/api/stats`
- **Method:** `GET`

**Description:**
Provides overall API statistics including total tickers, database size, cache hit rate, API request counts, and more.

**Example Response:**
```json
{
  "total_stock_tickers": 5000,
  "total_crypto_tickers": 250,
  "db_size": "100.00 MB",
  "cache_hit_rate": "100%",
  "api_requests_24h": 1000,
  "table_records": {
    "stock_quotes": 5000,
    "crypto_quotes": 250,
    "asset_prices_stock": 1000000,
    "asset_prices_crypto": 50000
  },
  "region_distribution": {
    "US": { "count": 4000, "percentage": 80.0 },
    "TH": { "count": 1000, "percentage": 20.0 }
  }
}
```

---

### 9. Trigger Full Sync
- **URL:** `/api/sync/full`
- **Method:** `POST`
- **Request Body:**
```json
{
  "ticker": "AAPL",
  "asset_type": "STOCK"
}
```

**Description:**
Initiates a full data synchronization. If a specific ticker is provided, only that ticker is synced; otherwise, a global sync is performed.

**Example Response:**
```json
{
  "message": "Full sync for stock ticker AAPL completed."
}
```

---

### 10. Trigger Delta Sync
- **URL:** `/api/sync/delta`
- **Method:** `POST`
- **Request Body:**
```json
{
  "ticker": "bitcoin",
  "asset_type": "CRYPTO"
}
```

**Description:**
Performs an incremental data synchronization for the specified ticker. If no ticker is specified, a global delta sync is executed.

**Example Response:**
```json
{
  "message": "Delta sync for crypto ticker bitcoin completed."
}
```

---

## Additional Notes
- **Caching:**
  - Top tickers are refreshed every 1 minute.
  - Regular entries use a 15-minute TTL.
  - Entries not found are cached for 24 hours.
- **Error Handling:**
  - Endpoints return appropriate HTTP status codes (e.g., 400, 404, 500) along with error messages.
- **Data Sources:**
  - Stock data is fetched from Yahoo Finance.
  - Cryptocurrency data is obtained from CoinGecko and Binance.
- **Synchronization:**
  - Full and delta sync endpoints update the database with the latest data from external APIs.

## Contact & Support
For issues or further information, please contact the API support team.