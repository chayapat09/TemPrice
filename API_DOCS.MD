Below is a detailed API documentation for the provided Flask application. This documentation covers each endpoint’s purpose, required and optional parameters, expected responses, and error conditions.

---

# API Documentation

This application provides endpoints for retrieving market data for stocks, cryptocurrencies, currencies, and also for managing “derived tickers” (which are computed using formulas). The API also includes endpoints for syncing data, checking system statistics, and viewing cached pricing information.

> **Note:**  
> – There is no authentication built into these endpoints.  
> – Rate limiting or access controls are not implemented at the API level.  
> – Many endpoints depend on a working database (SQLite by default) and external data sources (e.g. Yahoo Finance, Binance, AlphaVantage).

---

## Table of Contents

1. [Unified Ticker Data](#1-unified-ticker-data)
2. [Data Quality Metrics](#2-data-quality-metrics)
3. [Ticker Traffic](#3-ticker-traffic)
4. [Cache Information](#4-cache-information)
5. [Latest Price Data](#5-latest-price-data)
6. [Historical Data](#6-historical-data)
7. [Assets Listing](#7-assets-listing)
8. [System Statistics](#8-system-statistics)
9. [Ticker Search](#9-ticker-search)
10. [Full Sync Endpoints](#10-full-sync-endpoints)
11. [Delta Sync Endpoints](#11-delta-sync-endpoints)
12. [Derived Ticker Management](#12-derived-ticker-management)
13. [HTML Dashboard Endpoints](#13-html-dashboard-endpoints)

---

## 1. Unified Ticker Data

**Endpoint:**  
`GET /api/unified`

**Purpose:**  
Retrieve a unified view of ticker data—including the latest price (from cache), source information, and historical OHLCV records. If the ticker is “derived” (i.e. computed from other tickers), the endpoint evaluates the formula.

**Query Parameters:**  
- `ticker` (string, required): The ticker symbol to look up.

**Response Structure:**

- **For regular asset quotes (e.g. stocks, crypto, currency):**
  ```json
  {
    "ticker": "TSLAUSD",
    "source_ticker": "TSLA",
    "data_source": "yFinance",
    "from_asset": {
      "asset_type": "STOCK",
      "symbol": "TSLA"
    },
    "to_asset": {
      "asset_type": "CURRENCY",
      "symbol": "USD"
    },
    "latest_cache": {
      "price": 650.32,
      "timestamp": "2025-03-25T12:34:56.789123"
    },
    "historical_data": [
      {
        "date": "2025-03-24T00:00:00",
        "open": 640.0,
        "high": 660.0,
        "low": 635.0,
        "close": 650.32,
        "volume": 1234567.0
      },
      ...
    ]
  }
  ```

- **For derived tickers:**
  ```json
  {
    "ticker": "DERIVED1",
    "formula": "AAPL + MSFT",
    "asset_type": "DERIVED",
    "latest_price": 550.25,
    "historical_data": [
      {
        "date": "2025-03-24T00:00:00",
        "derived_value": 545.00
      },
      ...
    ]
  }
  ```

**Error Responses:**
- Missing `ticker` parameter:  
  ```json
  { "error": "Ticker parameter is required" }
  ```
- Ticker not found (neither an asset quote nor a derived ticker):  
  ```json
  { "error": "Ticker not found" }
  ```
- Database errors will return a 500 status with  
  ```json
  { "error": "Database error" }
  ```

---

## 2. Data Quality Metrics

**Endpoint:**  
`GET /api/data_quality`

**Purpose:**  
Provides metrics regarding the database quality and completeness.

**Response Structure:**
```json
{
  "total_assets": 150,
  "total_asset_quotes": 300,
  "total_ohlcv_records": 5000,
  "missing_name_assets": 5
}
```

**Error Responses:**  
Returns a 500 status with a message if a database error occurs.

---

## 3. Ticker Traffic

**Endpoint:**  
`GET /api/ticker_traffic`

**Purpose:**  
Returns a count of how many times each ticker has been queried via the API. The counts are maintained in memory using a global counter.

**Response Structure:**
```json
[
  { "ticker": "TSLAUSD", "asset_type": "STOCK", "count": 25 },
  { "ticker": "BTCUSDT", "asset_type": "CRYPTO", "count": 18 },
  ...
]
```

---

## 4. Cache Information

**Endpoint:**  
`GET /api/cache_info`

**Purpose:**  
Displays information about the caching system used for latest price data. Includes the timestamp of the last cache refresh and the time remaining until the next scheduled refresh.

**Response Structure:**
```json
{
  "last_cache_refresh": "2025-03-25T12:00:00.000000",
  "next_cache_refresh": "1 minutes"
}
```

---

## 5. Latest Price Data

**Endpoint:**  
`GET /api/latest`

**Purpose:**  
Retrieve the latest price for a given ticker.

**Query Parameters:**  
- `ticker` (string, required): The ticker symbol.
- `asset_type` (string, optional): The type of asset. Defaults to `"STOCK"`. Allowed values include `"STOCK"`, `"CRYPTO"`, `"CURRENCY"`, and `"DERIVED"`.

**Response Structure:**

- **For non-derived assets:**
  ```json
  {
    "ticker": "TSLAUSD",
    "asset_type": "STOCK",
    "price": 650.32,
    "timestamp": "2025-03-25T12:34:56.789123"
  }
  ```
- **For derived assets:**
  ```json
  {
    "ticker": "DERIVED1",
    "asset_type": "DERIVED",
    "price": 550.25,
    "formula": "AAPL + MSFT",
    "timestamp": "2025-03-25T12:34:56.789123"
  }
  ```

**Error Responses:**
- Missing `ticker` parameter:
  ```json
  { "error": "Ticker parameter is required" }
  ```
- If the ticker is not found:
  ```json
  { "error": "Ticker not found" }
  ```
- If there is an error evaluating a derived formula, a 500 status is returned with an error message.

---

## 6. Historical Data

**Endpoint:**  
`GET /api/historical`

**Purpose:**  
Return historical price data for the given ticker.

**Query Parameters:**  
- `ticker` (string, required): The ticker symbol.
- `asset_type` (string, optional): The asset type (default is `"STOCK"`).

**Response Structure:**

- **For regular asset quotes:**
  ```json
  {
    "ticker": "TSLAUSD",
    "historical_data": [
      {
        "date": "2025-03-24T00:00:00",
        "open": 640.0,
        "high": 660.0,
        "low": 635.0,
        "close": 650.32,
        "volume": 1234567.0
      },
      ...
    ]
  }
  ```
- **For derived tickers:**
  ```json
  {
    "ticker": "DERIVED1",
    "asset_type": "DERIVED",
    "formula": "AAPL + MSFT",
    "historical_data": [
      {
        "date": "2025-03-24T00:00:00",
        "derived_value": 545.00
      },
      ...
    ]
  }
  ```

**Error Responses:**
- Missing `ticker` parameter.
- If no historical data is found for the ticker, returns a 404 error.
- Database errors result in a 500 error.

---

## 7. Assets Listing

**Endpoint:**  
`GET /api/assets`

**Purpose:**  
List all assets (stocks, cryptocurrencies, currencies) stored in the system. An optional filter by asset type is available.

**Query Parameters:**  
- `asset_type` (string, optional): Filter by asset type (e.g. `"STOCK"`, `"CRYPTO"`, `"CURRENCY"`).

**Response Structure:**
```json
[
  {
    "asset_type": "STOCK",
    "symbol": "TSLA",
    "name": "Tesla, Inc.",
    "source_asset_key": "TSLA"
  },
  {
    "asset_type": "CRYPTO",
    "symbol": "BTC",
    "name": "Bitcoin",
    "source_asset_key": "bitcoin"
  },
  ...
]
```

**Error Responses:**  
Database errors yield a 500 error.

---

## 8. System Statistics

**Endpoint:**  
`GET /api/stats`

**Purpose:**  
Provide an overview of database statistics and API usage.

**Response Structure:**
```json
{
  "total_assets": 150,
  "total_asset_quotes": 300,
  "total_ohlcv_records": 5000,
  "db_size": "12.34 MB",
  "cache_hit_rate": "100%",
  "api_requests_24h": 125,
  "table_records": {
    "assets": 150,
    "asset_quotes": 300,
    "asset_ohlcv": 5000,
    "delta_sync_state": 1,
    "query_counts": 75
  }
}
```

**Error Responses:**  
A 500 error is returned if a database error occurs.

---

## 9. Ticker Search

**Endpoint:**  
`GET /api/tickers`

**Purpose:**  
Search for tickers using a query string. Supports pagination and an optional fuzzy matching mode.

**Query Parameters:**  
- `query` (string, required): The search term.
- `asset_type` (string, optional): If provided, restricts the search to either `"STOCK"`, `"CRYPTO"`, `"CURRENCY"`, or `"DERIVED"`.
- `limit` (integer, optional): Number of results per page (default is 10).
- `page` (integer, optional): Page number for paginated results (default is 1).
- `fuzzy` (string, optional): Set to `"true"` to enable fuzzy search matching.

**Response Structure:**  
A JSON array of matching tickers. Example for asset quotes:
```json
[
  {
    "ticker": "TSLAUSD",
    "source_ticker": "TSLA",
    "asset_type": "STOCK"
  },
  {
    "ticker": "AAPLUSD",
    "source_ticker": "AAPL",
    "asset_type": "STOCK"
  }
]
```
For derived tickers, the response includes a `formula` field:
```json
[
  {
    "ticker": "DERIVED1",
    "source_ticker": "",
    "asset_type": "DERIVED",
    "formula": "AAPL + MSFT"
  }
]
```

**Error Responses:**
- Missing query parameter:  
  ```json
  { "error": "Query parameter is required" }
  ```
- Invalid pagination parameters yield a 400 error.

---

## 10. Full Sync Endpoints

These endpoints trigger a full synchronization of data from external sources. They can be run globally (for all tickers) or for a specific ticker.

### a. Full Sync

**Endpoint:**  
`POST /api/sync/full`

**Request Body (JSON):**  
- `ticker` (string, optional): If provided, sync only this ticker.
- `asset_type` (string, optional): Defaults to `"STOCK"`. Supported values: `"STOCK"`, `"CRYPTO"`, `"CURRENCY"`.
- `data_source` (string, optional):  
  – For stocks, only `"YFINANCE"` is supported.  
  – For crypto, only `"BINANCE"` is supported.  
  – For currency, only `"ALPHAVANTAGE"` is supported.

**Response Structure:**
- For a specific ticker:
  ```json
  { "message": "Full sync for stock ticker TSLA completed using YFINANCE." }
  ```
- For a global sync:
  ```json
  { "message": "Global full sync for stocks completed." }
  ```

**Error Responses:**
- If `data_source` is invalid for the asset type:
  ```json
  { "error": "Invalid data source for STOCK. Supported: YFINANCE" }
  ```
- If ticker-specific data cannot be fetched, a 404 error is returned.
- Other errors return a 500 error with an appropriate message.

### b. Delta Sync

**Endpoint:**  
`POST /api/sync/delta`

**Purpose:**  
Perform a delta sync (update only recent data, typically the past 2 days) for a given ticker or globally.

**Request Body (JSON):**  
- `ticker` (string, optional)
- `asset_type` (string, optional, default `"STOCK"`)
- `data_source` (string, optional):  
  – For stocks: `"YFINANCE"`  
  – For crypto: `"BINANCE"`  
  – For currency: `"ALPHAVANTAGE"`

**Response Structure:**
- For a specific ticker:
  ```json
  { "message": "Delta sync for stock ticker TSLA completed using YFINANCE." }
  ```
- For a global sync:
  ```json
  { "message": "Global delta sync for stocks completed." }
  ```

**Error Responses:**  
Similar to the full sync endpoint, with error messages for invalid data sources or if ticker data is not found.

---

## 11. Derived Ticker Management

These endpoints allow you to manage “derived tickers,” which are computed from one or more underlying tickers using a formula.

### a. List Derived Tickers

**Endpoint:**  
`GET /api/derived`

**Response Structure:**
```json
[
  { "ticker": "DERIVED1", "formula": "AAPL + MSFT" },
  { "ticker": "DERIVED2", "formula": "GOOGL - FB" }
]
```

### b. Create a Derived Ticker

**Endpoint:**  
`POST /api/derived`

**Request Body (JSON):**
- `ticker` (string, required): Unique identifier for the derived ticker.
- `formula` (string, required): An arithmetic expression using one or more underlying ticker symbols.  
  _Example:_ `"AAPL + MSFT"`

**Response Structure:**
```json
{ "message": "Derived ticker DERIVED1 created successfully." }
```

**Error Responses:**
- Missing ticker or formula returns a 400 error.
- If the ticker already exists, a 400 error is returned with:
  ```json
  { "error": "Derived ticker with this ticker already exists" }
  ```

### c. Update a Derived Ticker

**Endpoint:**  
`PUT /api/derived/<ticker>`

**Path Parameter:**  
- `<ticker>`: The derived ticker identifier to update.

**Request Body (JSON):**
- `formula` (string, required): The new formula.

**Response Structure:**
```json
{ "message": "Derived ticker DERIVED1 updated successfully." }
```

**Error Responses:**
- Missing formula returns a 400 error.
- If the derived ticker is not found, a 404 error is returned.

### d. Delete a Derived Ticker

**Endpoint:**  
`DELETE /api/derived/<ticker>`

**Path Parameter:**  
- `<ticker>`: The derived ticker to delete.

**Response Structure:**
```json
{ "message": "Derived ticker DERIVED1 deleted successfully." }
```

**Error Responses:**
- If the ticker is not found, a 404 error is returned.

---

## 12. HTML Dashboard Endpoints

These endpoints serve HTML pages rather than JSON data.

### a. Derived Ticker Manager

**Endpoint:**  
`GET /derived_ticker_manager`

**Purpose:**  
Renders an HTML page for managing derived tickers.

### b. Dashboard

**Endpoint:**  
`GET /dashboard`

**Purpose:**  
Renders an HTML dashboard for viewing various statistics and metrics.

---

## Error Handling Summary

- **400 Bad Request:**  
  Returned when required parameters are missing or invalid (e.g., missing `ticker` or `query`).

- **404 Not Found:**  
  Returned when a ticker (or derived ticker) is not found.

- **500 Internal Server Error:**  
  Returned when there is a database error or an error during data processing/synchronization.

---

## Additional Notes

- **Cache & Sync:**  
  The app uses an in-memory cache (via the `latest_cache` dictionary) to store the most recent prices. Background jobs (configured via APScheduler) periodically refresh prices, perform delta syncs, and save query counts.

- **External Data Sources:**  
  – **Stocks:** Yahoo Finance via `yfinance`  
  – **Crypto:** Binance (and CoinGecko for metadata)  
  – **Currencies:** AlphaVantage  
  – **Derived Tickers:** Evaluated using a safe arithmetic expression evaluator

- **Database:**  
  Uses SQLAlchemy with an SQLite database (by default located at `instance/stock_data.db`).  
  Tables include `assets`, `asset_quotes`, `asset_ohlcv`, `delta_sync_state`, `query_counts`, and `derived_tickers`.

---

This documentation should help you understand and interact with the API endpoints provided by the application. Adjust parameters as needed and ensure that any external API keys or configurations (e.g., AlphaVantage API key) are properly set in the configuration file.