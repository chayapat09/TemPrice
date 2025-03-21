# Stock and Crypto Data API Documentation

## Introduction
This API provides access to stock and cryptocurrency data, including unified ticker information, latest prices, historical data, data quality metrics, and more. It also allows triggering full and delta syncs for data updates. The API is built using Flask and serves data from a SQLite database, with caching mechanisms to optimize performance.

## Base URL
All API endpoints use the following base URL:
```
/api
```

## General Information
- All API endpoints return data in **JSON** format.
- Dates and timestamps follow the **ISO 8601** format (e.g., `2023-10-01T12:00:00`).
- The API **does not** require authentication.
- Be mindful of **rate limits**, especially for endpoints that trigger syncs or fetch real-time data.

---

## Endpoints

### 1. Get Unified Ticker Data
- **URL:** `/unified`
- **Method:** `GET`
- **Query Parameters:**
  - `ticker` *(required, string)*: The ticker symbol of the asset (e.g., `AAPL` or `bitcoin`).
  - `asset_type` *(optional, string, default: "STOCK")*: Either `"STOCK"` or `"CRYPTO"`.

**Description:**  
Retrieves unified data for the specified ticker, including static quote data, the latest price from cache, and historical price data.

**Responses:**
- `200 OK`: JSON object containing `ticker`, `asset_type`, `quote_data`, `latest_cache`, and `historical_data`.
- `400 Bad Request`: If `ticker` is not provided.
- `404 Not Found`: If the `ticker` is not found in the database.

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
- **URL:** `/data_quality`
- **Method:** `GET`
- **Query Parameters:** None

**Description:**  
Provides data quality metrics, including the total number of stock and crypto tickers, missing fields in stock quotes, and duplicate price entries.

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
- **URL:** `/ticker_traffic`
- **Method:** `GET`
- **Query Parameters:** None

**Description:**  
Returns the query counts for each ticker and asset type, reflecting API usage frequency.

**Example Response:**
```json
[
  {"ticker": "AAPL", "asset_type": "STOCK", "count": 100},
  {"ticker": "bitcoin", "asset_type": "CRYPTO", "count": 50}
]
```

---

### 4. Get Cache Information
- **URL:** `/cache_info`
- **Method:** `GET`
- **Query Parameters:** None

**Description:**  
Provides information about the cache, including the last refresh time and the time until the next scheduled refresh.

**Example Response:**
```json
{
  "last_cache_refresh": "2023-10-01T12:00:00",
  "next_cache_refresh": "5 minutes"
}
```

---

### 5. Get Latest Price
- **URL:** `/latest`
- **Method:** `GET`
- **Query Parameters:**
  - `ticker` *(required, string)*
  - `asset_type` *(optional, string, default: "STOCK")*

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
- **URL:** `/assets`
- **Method:** `GET`
- **Query Parameters:**  
  - `asset_type` *(optional, string, default: "STOCK")*

**Description:**  
Lists all assets of the specified type with their latest prices from the cache.

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
- **URL:** `/historical`
- **Method:** `GET`
- **Query Parameters:**  
  - `ticker` *(required, string)*
  - `asset_type` *(optional, string, default: "STOCK")*

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
- **URL:** `/stats`
- **Method:** `GET`
- **Query Parameters:** None

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
    "US": {"count": 4000, "percentage": 80.0},
    "TH": {"count": 1000, "percentage": 20.0}
  }
}
```

---

### 9. Trigger Full Sync
- **URL:** `/sync/full`
- **Method:** `POST`
- **Request Body:**  
  ```json
  {
    "ticker": "AAPL",
    "asset_type": "STOCK"
  }
  ```

**Example Response:**
```json
{
  "message": "Full sync for stock ticker AAPL completed."
}
```

---

### 10. Trigger Delta Sync
- **URL:** `/sync/delta`
- **Method:** `POST`
- **Request Body:**  
  ```json
  {
    "ticker": "bitcoin",
    "asset_type": "CRYPTO"
  }
  ```

**Example Response:**
```json
{
  "message": "Delta sync for crypto ticker bitcoin completed."
}
```

---

## Notes
- Cache refresh:  
  - **Every 1 minute** for top tickers  
  - **15-minute TTL** for regular entries  
  - **24-hour TTL** for "not found" entries  

---

This API provides efficient stock and crypto market data retrieval with robust caching and sync capabilities.