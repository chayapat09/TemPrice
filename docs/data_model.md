# Stock Quote and Price Data Database Design Documentation

**Version:** 1.0  
**Date:** 2025-03-18

---

## 1. Introduction

This document details the relational database design for storing stock quote metadata and associated historical price data. It also describes the source data models for the fields used and provides a clear mapping between the source fields and our internal database model. This design supports data normalization, integrity, and efficient querying while remaining flexible for future enhancements.

---

## 2. Source Data Models

### 2.1 Source Stock Quote Data Model

The source dataset for stock quotes contains many fields, but for our purposes, only the following fields are used:

| Source Field                   | Data Type | Description                                                   |
|--------------------------------|-----------|---------------------------------------------------------------|
| **language**                   | string    | Language of the quote data                                    |
| **region**                     | string    | Geographic region                                             |
| **quoteType**                  | string    | Type of quote                                                 |
| **typeDisp**                   | string    | Display type                                                  |
| **quoteSourceName**            | string    | Name of the source providing the quote                        |
| **currency**                   | string    | Currency code                                                 |
| **exchange**                   | string    | Exchange identifier                                           |
| **market**                     | string    | Market information                                            |
| **fullExchangeName**           | string    | Full name of the exchange                                     |
| **longName**                   | string    | Extended or formal stock name                                 |
| **shortName**                  | string    | Abbreviated or short stock name                               |
| **symbol**                     | string    | Unique stock symbol                                             |
| **exchangeTimezoneName**       | string    | Full timezone name for the exchange                           |
| **exchangeTimezoneShortName**  | string    | Abbreviated timezone name                                     |
| **gmtOffSetMilliseconds**      | integer   | GMT offset in milliseconds                                    |
| **financialCurrency**          | string    | Currency used for financial reporting                         |
| **firstTradeDateMilliseconds** | integer   | First trade date represented in milliseconds                  |
| **messageBoardId**             | string    | Identifier for the message board                              |
| **displayName**                | string    | User-friendly display name for the stock                      |

### 2.2 Source Price Data Model

The price data is provided as a time series with a DatetimeIndex and the following relevant fields:

| Source Field  | Data Type | Description                                           |
|---------------|-----------|-------------------------------------------------------|
| **Date**      | Date      | Trading day (provided by the DatetimeIndex)           |
| **Open**      | float     | Opening price for the trading day                     |
| **High**      | float     | Highest price during the trading day                  |
| **Low**       | float     | Lowest price during the trading day                   |
| **Close**     | float     | Closing price for the trading day                     |
| **Volume**    | integer   | Trading volume for the day                            |

---

## 3. Database Design

Our database design consists of two main tables: **StockQuotes** and **PriceData**. These tables are related via the stock symbol.

### 3.1 StockQuotes Table

This table stores the metadata for each stock quote.

**Fields and Their Mappings:**

| Database Field                   | Data Type   | Mapped Source Field             |
|----------------------------------|-------------|---------------------------------|
| **symbol** (Primary Key)         | VARCHAR     | symbol                          |
| **language**                     | VARCHAR     | language                        |
| **region**                       | VARCHAR     | region                          |
| **quote_type**                   | VARCHAR     | quoteType                       |
| **type_disp**                    | VARCHAR     | typeDisp                        |
| **quote_source_name**            | VARCHAR     | quoteSourceName                 |
| **currency**                     | VARCHAR     | currency                        |
| **exchange**                     | VARCHAR     | exchange                        |
| **market**                       | VARCHAR     | market                          |
| **full_exchange_name**           | VARCHAR     | fullExchangeName                |
| **long_name**                    | VARCHAR     | longName                        |
| **short_name**                   | VARCHAR     | shortName                       |
| **exchange_timezone_name**       | VARCHAR     | exchangeTimezoneName            |
| **exchange_timezone_short_name** | VARCHAR     | exchangeTimezoneShortName       |
| **gmt_offset_milliseconds**      | BIGINT      | gmtOffSetMilliseconds           |
| **financial_currency**           | VARCHAR     | financialCurrency               |
| **first_trade_date_milliseconds**| BIGINT      | firstTradeDateMilliseconds      |
| **message_board_id**             | VARCHAR     | messageBoardId                  |
| **display_name**                 | VARCHAR     | displayName                     |

**SQL DDL Example:**

```sql
CREATE TABLE StockQuotes (
    symbol VARCHAR(20) PRIMARY KEY,
    language VARCHAR(50),
    region VARCHAR(50),
    quote_type VARCHAR(50),
    type_disp VARCHAR(50),
    quote_source_name VARCHAR(100),
    currency VARCHAR(10),
    exchange VARCHAR(50),
    market VARCHAR(50),
    full_exchange_name VARCHAR(100),
    long_name VARCHAR(200),
    short_name VARCHAR(100),
    exchange_timezone_name VARCHAR(100),
    exchange_timezone_short_name VARCHAR(20),
    gmt_offset_milliseconds BIGINT,
    financial_currency VARCHAR(10),
    first_trade_date_milliseconds BIGINT,
    message_board_id VARCHAR(50),
    display_name VARCHAR(100)
);
```

### 3.2 PriceData Table

This table stores the historical price data for each stock quote.

**Fields and Their Mappings:**

| Database Field | Data Type | Mapped Source Field                 |
|----------------|-----------|-------------------------------------|
| **symbol**     | VARCHAR   | symbol (from the StockQuotes model) |
| **date**       | DATE      | Date (from the DatetimeIndex)        |
| **open**       | FLOAT     | Open                                |
| **high**       | FLOAT     | High                                |
| **low**        | FLOAT     | Low                                 |
| **close**      | FLOAT     | Close                               |
| **volume**     | INTEGER   | Volume                              |

**Key Constraints:**
- **Composite Primary Key:** (symbol, date)
- **Foreign Key Constraint:** `symbol` references `StockQuotes(symbol)`

**SQL DDL Example:**

```sql
CREATE TABLE PriceData (
    symbol VARCHAR(20),
    date DATE,
    open FLOAT,
    high FLOAT,
    low FLOAT,
    close FLOAT,
    volume INTEGER,
    PRIMARY KEY (symbol, date),
    FOREIGN KEY (symbol) REFERENCES StockQuotes(symbol)
);
```

---

## 4. Mapping Between Source Data Model and Database Model

This section outlines the mapping between the fields in the source datasets and the corresponding fields in our database tables.

### 4.1 Mapping for Stock Quote Data

| Source Field                    | Source Type | Mapped Field in StockQuotes          | Database Type |
|---------------------------------|-------------|--------------------------------------|---------------|
| language                        | string      | language                             | VARCHAR       |
| region                          | string      | region                               | VARCHAR       |
| quoteType                       | string      | quote_type                           | VARCHAR       |
| typeDisp                        | string      | type_disp                            | VARCHAR       |
| quoteSourceName                 | string      | quote_source_name                    | VARCHAR       |
| currency                        | string      | currency                             | VARCHAR       |
| exchange                        | string      | exchange                             | VARCHAR       |
| market                          | string      | market                               | VARCHAR       |
| fullExchangeName                | string      | full_exchange_name                   | VARCHAR       |
| longName                        | string      | long_name                            | VARCHAR       |
| shortName                       | string      | short_name                           | VARCHAR       |
| symbol                          | string      | symbol (Primary Key)                 | VARCHAR       |
| exchangeTimezoneName            | string      | exchange_timezone_name               | VARCHAR       |
| exchangeTimezoneShortName       | string      | exchange_timezone_short_name         | VARCHAR       |
| gmtOffSetMilliseconds           | integer     | gmt_offset_milliseconds              | BIGINT        |
| financialCurrency               | string      | financial_currency                   | VARCHAR       |
| firstTradeDateMilliseconds      | integer     | first_trade_date_milliseconds        | BIGINT        |
| messageBoardId                  | string      | message_board_id                     | VARCHAR       |
| displayName                     | string      | display_name                         | VARCHAR       |

### 4.2 Mapping for Price Data

| Source Field   | Source Type | Mapped Field in PriceData |
|----------------|-------------|---------------------------|
| Open           | float       | open                      |
| High           | float       | high                      |
| Low            | float       | low                       |
| Close          | float       | close                     |
| Volume         | integer     | volume                    |
| Date           | Date        | date                      |

*Note:* The `Date` field is derived from the DatetimeIndex of the price data.

---

## 5. Conclusion

This documentation provides a complete overview of the database design, including:

- **Source Data Models:** The fields and types from the original stock quote and price datasets.
- **Database Schema:** Two tables (**StockQuotes** and **PriceData**) that store the respective metadata and time series data.
- **Mapping:** A detailed mapping between the source fields and the corresponding database fields.

This design facilitates data normalization, ensures referential integrity, and supports efficient querying and analysis. It serves as a reference for developers and database administrators for implementing and maintaining the stock data system.

