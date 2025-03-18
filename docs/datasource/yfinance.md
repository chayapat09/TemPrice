Below is a reformatted version of the documentation that preserves the complete code output exactly as provided, without trimming any parts.

---

# YFinance Data Fetching Utility Documentation

This utility uses the **yfinance** library to fetch stock quotes and download daily historical data starting from January 1, 2020. It is designed to handle both complete and sample data retrieval via an `EquityQuery`.

---

## Overview

The code consists of two examples:

1. **Full Data Fetching:** Retrieves all symbols matching the query and downloads their historical data in batches.
2. **Sample Data Fetching:** Retrieves a sample of symbols and downloads historical data for only a subset of tickers.

Both examples demonstrate how to use the `fetch_yf_data` function with slightly different parameters to support various use cases.

---

## Function: `fetch_yf_data`

### Purpose

- **Fetch Quotes:** Uses an `EquityQuery` to retrieve a list of stock quotes.
- **Download Historical Data:** Downloads daily historical data (starting from 2020-01-01) for each ticker symbol.

### Parameters

- **`max_tickers_per_request (int)`**  
  Maximum number of tickers to include in a single batch request.

- **`delay_t (int or float)`**  
  Delay in seconds between batch requests to avoid overwhelming the server.

- **`query (EquityQuery)`**  
  An instance of `EquityQuery` used to filter symbols.

- **`sample_size (int)`** *(Optional, only in sample fetching)*  
  Number of sample tickers for which to fetch data.

### Returns

- **`quotes_df (pd.DataFrame)`**  
  DataFrame containing all the fetched quotes.

- **`historical_data (dict)`**  
  Dictionary where each key is a ticker symbol and its value is a DataFrame containing the ticker’s historical data.

---

## Detailed Process

### 1. Retrieve Symbols via `EquityQuery`

- **Batch Retrieval:**  
  The function starts by fetching symbols in batches. It uses an offset and a fixed batch size (set to 250) until no further quotes are returned.

- **Building the DataFrame:**  
  All retrieved quotes are aggregated into a Pandas DataFrame (`quotes_df`). The structure and first few rows of this DataFrame are printed for inspection.

- **Extracting Symbols:**  
  The ticker symbols are extracted from the quotes for subsequent historical data downloads.

### 2. Download Daily Historical Data

- **Batch Processing:**  
  The list of symbols is divided into batches (as determined by `max_tickers_per_request`). For each batch, a space-separated string of tickers is generated and passed to `yf.download`.

- **Handling Multi-Index DataFrames:**  
  If data for multiple tickers is returned (resulting in a MultiIndex DataFrame), the code extracts each ticker’s data individually.  
  If only a single ticker is returned, it is processed as a standard DataFrame.

- **Logging:**  
  For each ticker, the function prints:
  - The number of rows of historical data.
  - The date range (from the earliest to the latest date).
  - Warnings or error messages if data is missing or a ticker is not found in the batch.

- **Delay Between Requests:**  
  A delay (as specified by `delay_t`) is inserted between batch requests.

---

## Example Code Usage

### Full Data Fetching Example

```python
import yfinance as yf
from yfinance import EquityQuery
import pandas as pd
import time

def fetch_yf_data(max_tickers_per_request, delay_t, query):
    """
    Fetches quotes using an EquityQuery and downloads daily historical data starting from 2020-01-01 for each ticker.
    
    Parameters:
      max_tickers_per_request (int): Maximum number of tickers to download per batch.
      delay_t (int or float): Delay (in seconds) between each batch request.
      query (EquityQuery): An EquityQuery instance to filter the symbols.
    
    Returns:
      quotes_df (pd.DataFrame): DataFrame of all fetched quotes.
      historical_data (dict): Dictionary with ticker as key and its historical data DataFrame as value.
    """
    # -------------------------------
    # Step 1: Retrieve All Symbols via EquityQuery
    # -------------------------------
    print("Starting symbol retrieval via EquityQuery.")
    offset = 0
    size = 250  # Maximum quotes per request as allowed by Yahoo Finance
    all_quotes = []

    while True:
        result = yf.screen(query, offset=offset, size=size)
        quotes = result.get("quotes", [])
        print(f"Fetched {len(quotes)} quotes at offset {offset}.")
        
        if not quotes:
            break

        all_quotes.extend(quotes)
        offset += size

    # Save quotes to a DataFrame and display its structure
    quotes_df = pd.DataFrame(all_quotes)
    print("\nQuotes DataFrame structure:")
    print(quotes_df.info())
    print("\nFirst few rows of Quotes DataFrame:")
    print(quotes_df.head())

    # Extract symbols from quotes
    symbols = [quote.get("symbol") for quote in all_quotes if quote.get("symbol")]
    print(f"\nTotal symbols found: {len(symbols)}")

    # -------------------------------
    # Step 2: Download Daily Historical Data from 2020-01-01 for All Symbols
    # -------------------------------
    historical_data = {}  # Dictionary to store historical data for each ticker

    for i in range(0, len(symbols), max_tickers_per_request):
        batch_symbols = symbols[i:i+max_tickers_per_request]
        tickers_str = " ".join(batch_symbols)
        print(f"\nDownloading historical data for tickers: {batch_symbols}")
        
        # Download historical data for the batch using start date "2020-01-01"
        data = yf.download(tickers=tickers_str, start="2020-01-01", interval="1d", group_by='ticker')
        print(f"Downloaded data columns: {data.columns}")
        
        # Check if data is multi-indexed (multiple tickers)
        if isinstance(data.columns, pd.MultiIndex):
            available_tickers = data.columns.get_level_values(0).unique().tolist()
            print(f"Available tickers in data: {available_tickers}")
            
            for ticker in batch_symbols:
                if ticker in available_tickers:
                    try:
                        ticker_data = data[ticker]
                        historical_data[ticker] = ticker_data
                        if not ticker_data.empty:
                            start_date = ticker_data.index.min().strftime("%Y-%m-%d")
                            end_date = ticker_data.index.max().strftime("%Y-%m-%d")
                            print(f"Ticker {ticker}: {len(ticker_data)} rows from {start_date} to {end_date}.")
                        else:
                            print(f"WARNING: No data returned for ticker: {ticker}")
                    except Exception as e:
                        print(f"ERROR: Exception for ticker {ticker}: {e}")
                else:
                    print(f"ERROR: Ticker {ticker} not found in downloaded batch data. Available: {available_tickers}")
        else:
            # If only one ticker is returned, data is a regular DataFrame.
            ticker = batch_symbols[0]
            historical_data[ticker] = data
            if not data.empty:
                start_date = data.index.min().strftime("%Y-%m-%d")
                end_date = data.index.max().strftime("%Y-%m-%d")
                print(f"Ticker {ticker}: {len(data)} rows from {start_date} to {end_date}.")
            else:
                print(f"WARNING: No data returned for ticker: {ticker}")
        
        print(f"Sleeping for {delay_t} seconds between requests.")
        time.sleep(delay_t)

    print(f"\nHistorical data downloaded for {len(historical_data)} tickers.")
    for ticker, df in historical_data.items():
        print(f"Ticker {ticker}: {len(df)} rows; Columns: {df.columns.tolist()}")
    
    return quotes_df, historical_data

# -------------------------------
# Example usage:
# -------------------------------
if __name__ == "__main__":
    # Define your query. For example, this query fetches stocks with region 'th'
    query = EquityQuery('eq', ['region', 'th'])
    
    # Set the adjustable parameters
    max_tickers_per_request = 25  # Maximum tickers per request
    delay_t = 1                   # Delay (in seconds) between requests

    # Fetch data using the parameters
    quotes_df, historical_data = fetch_yf_data(max_tickers_per_request, delay_t, query)
```

---

### Sample Data Fetching Example

This example fetches a **sample** of tickers (e.g., 10) and downloads their historical data. It prints a sample of the data and its detailed structure for each ticker.

```python
import yfinance as yf
from yfinance import EquityQuery
import pandas as pd
import time

def fetch_yf_data(max_tickers_per_request, delay_t, query, sample_size=10):
    """
    Fetches a sample of quotes using an EquityQuery and downloads daily historical data starting from 2020-01-01
    for a sample of tickers. For each ticker, the code prints the first few rows (head) and the DataFrame info.
    
    Parameters:
      max_tickers_per_request (int): Maximum number of tickers to download per batch.
      delay_t (int or float): Delay (in seconds) between each batch request.
      query (EquityQuery): An EquityQuery instance to filter the symbols.
      sample_size (int): Number of sample tickers to fetch data for.
    
    Returns:
      quotes_df (pd.DataFrame): DataFrame of fetched quotes.
      historical_data (dict): Dictionary with ticker as key and its historical data DataFrame as value.
    """
    # -------------------------------
    # Retrieve a sample of symbols via EquityQuery
    # -------------------------------
    result = yf.screen(query, offset=0, size=sample_size)
    all_quotes = result.get("quotes", [])
    
    # Convert quotes to DataFrame and log essential information to understand its data model
    quotes_df = pd.DataFrame(all_quotes)
    print("Quotes DataFrame (sample):")
    print(quotes_df.head())
    print("\nQuotes DataFrame info:")
    print(quotes_df.info())
    
    # Extract sample symbols from quotes
    symbols = [quote.get("symbol") for quote in all_quotes if quote.get("symbol")]
    print(f"\nSample tickers: {symbols}")
    
    # -------------------------------
    # Download Historical Data from 2020-01-01 for the Sample Tickers
    # -------------------------------
    historical_data = {}
    for i in range(0, len(symbols), max_tickers_per_request):
        batch_symbols = symbols[i:i+max_tickers_per_request]
        tickers_str = " ".join(batch_symbols)
        
        # Download historical data using start date "2020-01-01"
        data = yf.download(tickers=tickers_str, start="2020-01-01", interval="1d", group_by='ticker')
        
        if isinstance(data.columns, pd.MultiIndex):
            for ticker in batch_symbols:
                if ticker in data.columns.get_level_values(0):
                    ticker_data = data[ticker]
                    historical_data[ticker] = ticker_data
                    print(f"\nTicker: {ticker}")
                    print(f"Historical data shape: {ticker_data.shape}")
                    print("Data Sample (head):")
                    print(ticker_data.head())
                    print("Data Info:")
                    ticker_data.info()
                else:
                    print(f"\nTicker {ticker} not found in downloaded historical data.")
        else:
            # Single ticker returned
            ticker = batch_symbols[0]
            historical_data[ticker] = data
            print(f"\nTicker: {ticker}")
            print(f"Historical data shape: {data.shape}")
            print("Data Sample (head):")
            print(data.head())
            print("Data Info:")
            data.info()
        
        time.sleep(delay_t)
    
    return quotes_df, historical_data

# -------------------------------
# Example usage:
# -------------------------------
if __name__ == "__main__":
    # Example query: fetching stocks with region 'th'
    query = EquityQuery('eq', ['region', 'th'])
    max_tickers_per_request = 25  # Maximum tickers per request
    delay_t = 1                   # Delay (in seconds) between requests

    # Fetch sample data using the parameters
    quotes_df, historical_data = fetch_yf_data(max_tickers_per_request, delay_t, query, sample_size=10)
```

---

## Expected Output

### Standard Output (Using Region 'th')

A sample output of the quotes DataFrame and historical data is printed. (Refer to the code output printed during the function execution.)

---

## Additional Example: US Region Output

By changing the query region from `'th'` to `'us'`, you can retrieve quotes and historical data for US stocks. For example, change the query as follows:

```python
query = EquityQuery('eq', ['region', 'us'])
```

This configuration yields a sample output similar to the following:

```
[                       0%                       ]Quotes DataFrame (sample):
  language region quoteType typeDisp         quoteSourceName  triggerable  \
0    en-US     US    EQUITY   Equity           Delayed Quote        False   
1    en-US     US    EQUITY   Equity  Nasdaq Real Time Price         True   
2    en-US     US    EQUITY   Equity  Nasdaq Real Time Price         True   
3    en-US     US    EQUITY   Equity           Delayed Quote        False   
4    en-US     US    EQUITY   Equity  Nasdaq Real Time Price        False   

  customPriceAlertConfidence currency  regularMarketChangePercent  bookValue  \
0                        LOW      USD                  -83.218180     -0.959   
1                       HIGH      USD                   -2.356900      1.120   
2                       HIGH      USD                    2.693877      4.912   
3                        LOW      USD                    2.000003      6.168   
4                        LOW      USD                    0.896897      9.317   

   ...  trailingPE  epsForward  epsCurrentYear  priceEpsCurrentYear  \
0  ...         NaN         NaN             NaN                  NaN   
1  ...    32.22222        0.48        -0.49000            -5.918367   
2  ...         NaN       -1.68        -1.73096            -7.267644   
3  ...    76.50001         NaN             NaN                  NaN   
4  ...    36.77747        1.34         1.34292            24.921440   

   averageAnalystRating  ipoExpectedDate             prevName  nameChangeDate  \
0                   NaN              NaN                  NaN             NaN   
1            2.7 - Hold              NaN                  NaN             NaN   
2      1.5 - Strong Buy       2022-12-16                  NaN             NaN   
3                   NaN       2025-01-07                  NaN             NaN   
4                   NaN              NaN  Rexnord Corporation      2025-03-17   

   dividendRate  dividendYield  
0           NaN            NaN  
1           NaN            NaN  
2           NaN            NaN  
3           NaN            NaN  
4          0.36           1.09  

[5 rows x 89 columns]

Quotes DataFrame info:
<class 'pandas.core.frame.DataFrame'>
RangeIndex: 10 entries, 0 to 9
Data columns (total 89 columns):
 #   Column                             Non-Null Count  Dtype  
---  ------                             --------------  -----  
 0   language                           10 non-null     object 
 1   region                             10 non-null     object 
 2   quoteType                          10 non-null     object 
 3   typeDisp                           10 non-null     object 
 4   quoteSourceName                    10 non-null     object 
 5   triggerable                        10 non-null     bool   
 6   customPriceAlertConfidence         10 non-null     object 
 7   currency                           10 non-null     object 
 8   regularMarketChangePercent         10 non-null     float64
 9   bookValue                          10 non-null     float64
 10  fiftyDayAverage                    10 non-null     float64
 11  fiftyDayAverageChange              10 non-null     float64
 12  fiftyDayAverageChangePercent       10 non-null     float64
 13  twoHundredDayAverage               10 non-null     float64
 14  twoHundredDayAverageChange         10 non-null     float64
 15  twoHundredDayAverageChangePercent  10 non-null     float64
 16  marketCap                          10 non-null     int64  
 17  priceToBook                        10 non-null     float64
 18  sourceInterval                     10 non-null     int64  
 19  exchangeDataDelayedBy              10 non-null     int64  
 20  exchangeTimezoneName               10 non-null     object 
 21  exchangeTimezoneShortName          10 non-null     object 
 22  gmtOffSetMilliseconds              10 non-null     int64  
 23  esgPopulated                       10 non-null     bool   
 24  tradeable                          10 non-null     bool   
 25  cryptoTradeable                    10 non-null     bool   
 26  hasPrePostMarketData               10 non-null     bool   
 27  firstTradeDateMilliseconds         10 non-null     int64  
 28  priceHint                          10 non-null     int64  
 29  regularMarketChange                10 non-null     float64
 30  regularMarketTime                  10 non-null     int64  
 31  regularMarketPrice                 10 non-null     float64
 32  regularMarketDayHigh               10 non-null     float64
 33  regularMarketDayRange              10 non-null     object 
 34  regularMarketDayLow                10 non-null     float64
 35  regularMarketVolume                10 non-null     int64  
 36  regularMarketPreviousClose         10 non-null     float64
 37  bid                                10 non-null     float64
 38  ask                                10 non-null     float64
 39  bidSize                            10 non-null     int64  
 40  askSize                            10 non-null     int64  
 41  market                             10 non-null     object 
 42  messageBoardId                     10 non-null     object 
 43  fullExchangeName                   10 non-null     object 
 44  longName                           10 non-null     object 
 45  financialCurrency                  10 non-null     object 
 46  regularMarketOpen                  10 non-null     float64
 47  averageDailyVolume3Month           10 non-null     int64  
 48  averageDailyVolume10Day            10 non-null     int64  
 49  corporateActions                   10 non-null     object 
 50  fiftyTwoWeekLowChange              10 non-null     float64
 51  fiftyTwoWeekLowChangePercent       10 non-null     float64
 52  fiftyTwoWeekRange                  10 non-null     object 
 53  fiftyTwoWeekHighChange             10 non-null     float64
 54  fiftyTwoWeekHighChangePercent      10 non-null     float64
 55  fiftyTwoWeekChangePercent          10 non-null     float64
 56  trailingAnnualDividendRate         10 non-null     float64
 57  trailingAnnualDividendYield        10 non-null     float64
 58  marketState                        10 non-null     object 
 59  epsTrailingTwelveMonths            10 non-null     float64
 60  sharesOutstanding                  10 non-null     int64  
 61  exchange                           10 non-null     object 
 62  fiftyTwoWeekHigh                   10 non-null     float64
 63  fiftyTwoWeekLow                    10 non-null     float64
 64  shortName                          10 non-null     object 
 65  displayName                        9 non-null      object 
 66  symbol                             10 non-null     object 
 67  forwardPE                          6 non-null      float64
 68  postMarketChangePercent            5 non-null      float64
 69  postMarketTime                     5 non-null      float64
 70  postMarketPrice                    5 non-null      float64
 71  postMarketChange                   5 non-null      float64
 72  dividendDate                       3 non-null      float64
 73  earningsTimestamp                  5 non-null      float64
 74  earningsTimestampStart             6 non-null      float64
 75  earningsTimestampEnd               6 non-null      float64
 76  earningsCallTimestampStart         5 non-null      float64
 77  earningsCallTimestampEnd           5 non-null      float64
 78  isEarningsDateEstimate             6 non-null      object 
 79  trailingPE                         4 non-null      float64
 80  epsForward                         6 non-null      float64
 81  epsCurrentYear                     5 non-null      float64
 82  priceEpsCurrentYear                5 non-null      float64
 83  averageAnalystRating               4 non-null      object 
 84  ipoExpectedDate                    3 non-null      object 
 85  prevName                           2 non-null      object 
 86  nameChangeDate                     2 non-null      object 
 87  dividendRate                       1 non-null      float64
 88  dividendYield                      1 non-null      float64
dtypes: bool(5), float64(44), int64(13), object(27)
memory usage: 6.7+ KB
None

Sample tickers: ['ZZZOF', 'ZYXI', 'ZYME', 'ZYBT', 'ZWS', 'ZVTK', 'ZVSA', 'ZVRA', 'ZVLO', 'ZVIA']
[*********************100%***********************]  10 of 10 completed

Ticker: ZZZOF
Historical data shape: (1308, 5)
Data Sample (head):
Price        Open  High    Low  Close  Volume
Date                                         
2020-01-02  1.160  1.54  0.600   1.54   165.0
2020-01-03  0.954  1.16  0.954   1.16    21.0
2020-01-06  1.160  1.54  0.500   1.54   578.0
2020-01-07  1.540  1.54  1.540   1.54     0.0
2020-01-08  1.540  1.54  1.540   1.54     0.0
Data Info:
<class 'pandas.core.frame.DataFrame'>
DatetimeIndex: 1308 entries, 2020-01-02 to 2025-03-17
Data columns (total 5 columns):
 #   Column  Non-Null Count  Dtype  
---  ------  --------------  -----  
 0   Open    1307 non-null   float64
 1   High    1307 non-null   float64
 2   Low     1307 non-null   float64
 3   Close   1307 non-null   float64
 4   Volume  1307 non-null   float64
dtypes: float64(5)
memory usage: 61.3 KB

Ticker: ZYXI
Historical data shape: (1308, 5)
Data Sample (head):
Price           Open      High       Low     Close  Volume
Date                                                      
2020-01-02  7.148011  7.192967  6.995160  7.121037  139040
2020-01-03  7.022134  7.615553  7.022134  7.507659  294690
2020-01-06  7.552615  7.732439  7.354809  7.570597  172590
2020-01-07  7.642527  7.777395  7.516650  7.678492  128040
2020-01-08  7.660510  7.777395  7.516650  7.615553  171600
Data Info:
<class 'pandas.core.frame.DataFrame'>
DatetimeIndex: 1308 entries, 2020-01-02 to 2025-03-17
Data columns (total 5 columns):
 #   Column  Non-Null Count  Dtype  
---  ------  --------------  -----  
 0   Open    1308 non-null   float64
 1   High    1308 non-null   float64
 2   Low     1308 non-null   float64
 3   Close   1308 non-null   float64
 4   Volume  1308 non-null   int64  
dtypes: float64(4), int64(1)
memory usage: 61.3 KB

Ticker: ZYME
Historical data shape: (1308, 5)
Data Sample (head):
Price            Open       High        Low      Close  Volume
Date                                                          
2020-01-02  45.650002  47.840000  45.000000  47.590000  301100
2020-01-03  47.000000  47.599998  45.235001  45.860001  262000
2020-01-06  45.639999  45.840000  44.240002  45.060001  429500
2020-01-07  44.810001  46.980000  44.094002  46.500000  248000
2020-01-08  46.500000  47.650002  45.000000  46.139999  203500
Data Info:
<class 'pandas.core.frame.DataFrame'>
DatetimeIndex: 1308 entries, 2020-01-02 to 2025-03-17
Data columns (total 5 columns):
 #   Column  Non-Null Count  Dtype  
---  ------  --------------  -----  
 0   Open    1308 non-null   float64
 1   High    1308 non-null   float64
 2   Low     1308 non-null   float64
 3   Close   1308 non-null   float64
 4   Volume  1308 non-null   int64  
dtypes: float64(4), int64(1)
memory usage: 61.3 KB

Ticker: ZYBT
Historical data shape: (1308, 5)
Data Sample (head):
Price       Open  High  Low  Close  Volume
Date                                      
2020-01-02   NaN   NaN  NaN    NaN     NaN
2020-01-03   NaN   NaN  NaN    NaN     NaN
2020-01-06   NaN   NaN  NaN    NaN     NaN
2020-01-07   NaN   NaN  NaN    NaN     NaN
2020-01-08   NaN   NaN  NaN    NaN     NaN
Data Info:
<class 'pandas.core.frame.DataFrame'>
DatetimeIndex: 1308 entries, 2020-01-02 to 2025-03-17
Data columns (total 5 columns):
 #   Column  Non-Null Count  Dtype  
---  ------  --------------  -----  
 0   Open    47 non-null     float64
 1   High    47 non-null     float64
 2   Low     47 non-null     float64
 3   Close   47 non-null     float64
 4   Volume  47 non-null     float64
dtypes: float64(5)
memory usage: 61.3 KB

Ticker: ZWS
Historical data shape: (1308, 5)
Data Sample (head):
Price            Open       High        Low      Close  Volume
Date                                                          
2020-01-02  31.552471  31.619584  31.188145  31.485359  809900
2020-01-03  30.996395  31.504531  30.881342  31.456594  830900
2020-01-06  31.130617  31.303192  30.919691  31.303192  695900
2020-01-07  31.245666  31.341539  31.015564  31.197729  604300
2020-01-08  31.197731  31.466179  31.188141  31.226492  751200
Data Info:
<class 'pandas.core.frame.DataFrame'>
DatetimeIndex: 1308 entries, 2020-01-02 to 2025-03-17
Data columns (total 5 columns):
 #   Column  Non-Null Count  Dtype  
---  ------  --------------  -----  
 0   Open    1308 non-null   float64
 1   High    1308 non-null   float64
 2   Low     1308 non-null   float64
 3   Close   1308 non-null   float64
 4   Volume  1308 non-null   int64  
dtypes: float64(4), int64(1)
memory usage: 61.3 KB

Ticker: ZVTK
Historical data shape: (1308, 5)
Data Sample (head):
Price         Open    High     Low   Close    Volume
Date                                                
2020-01-02  0.0351  0.0360  0.0351  0.0351   23451.0
2020-01-03  0.0388  0.0470  0.0388  0.0470  139023.0
2020-01-06  0.0470  0.0470  0.0350  0.0370  106102.0
2020-01-07  0.0370  0.0370  0.0340  0.0340  200001.0
2020-01-08  0.0369  0.0369  0.0340  0.0340   18002.0
Data Info:
<class 'pandas.core.frame.DataFrame'>
DatetimeIndex: 1308 entries, 2020-01-02 to 2025-03-17
Data columns (total 5 columns):
 #   Column  Non-Null Count  Dtype  
---  ------  --------------  -----  
 0   Open    1307 non-null   float64
 1   High    1307 non-null   float64
 2   Low     1307 non-null   float64
 3   Close   1307 non-null   float64
 4   Volume  1307 non-null   float64
dtypes: float64(5)
memory usage: 61.3 KB

Ticker: ZVSA
Historical data shape: (1308, 5)
Data Sample (head):
Price       Open  High  Low  Close  Volume
Date                                      
2020-01-02   NaN   NaN  NaN    NaN     NaN
2020-01-03   NaN   NaN  NaN    NaN     NaN
2020-01-06   NaN   NaN  NaN    NaN     NaN
2020-01-07   NaN   NaN  NaN    NaN     NaN
2020-01-08   NaN   NaN  NaN    NaN     NaN
Data Info:
<class 'pandas.core.frame.DataFrame'>
DatetimeIndex: 1308 entries, 2020-01-02 to 2025-03-17
Data columns (total 5 columns):
 #   Column  Non-Null Count  Dtype  
---  ------  --------------  -----  
 0   Open    775 non-null    float64
 1   High    775 non-null    float64
 2   Low     775 non-null    float64
 3   Close   775 non-null    float64
 4   Volume  775 non-null    float64
dtypes: float64(5)
memory usage: 61.3 KB

Ticker: ZVRA
Historical data shape: (1308, 5)
Data Sample (head):
Price        Open   High    Low  Close  Volume
Date                                          
2020-01-02  6.240  6.880  6.096  6.480   62644
2020-01-03  6.400  7.360  6.160  6.560  101125
2020-01-06  6.560  7.200  6.560  6.928   88131
2020-01-07  6.816  8.944  6.816  8.640  247856
2020-01-08  8.640  8.736  7.536  8.192  120556
Data Info:
<class 'pandas.core.frame.DataFrame'>
DatetimeIndex: 1308 entries, 2020-01-02 to 2025-03-17
Data columns (total 5 columns):
 #   Column  Non-Null Count  Dtype  
---  ------  --------------  -----  
 0   Open    1308 non-null   float64
 1   High    1308 non-null   float64
 2   Low     1308 non-null   float64
 3   Close   1308 non-null   float64
 4   Volume  1308 non-null   int64  
dtypes: float64(4), int64(1)
memory usage: 61.3 KB

Ticker: ZVLO
Historical data shape: (1308, 5)
Data Sample (head):
Price       Open  High   Low  Close  Volume
Date                                       
2020-01-02  0.05  0.05  0.05   0.05     0.0
2020-01-03  0.05  0.05  0.05   0.05     0.0
2020-01-06  0.05  0.05  0.05   0.05     0.0
2020-01-07  0.05  0.05  0.05   0.05   100.0
2020-01-08  0.05  0.05  0.05   0.05   225.0
Data Info:
<class 'pandas.core.frame.DataFrame'>
DatetimeIndex: 1308 entries, 2020-01-02 to 2025-03-17
Data columns (total 5 columns):
 #   Column  Non-Null Count  Dtype  
---  ------  --------------  -----  
 0   Open    1307 non-null   float64
 1   High    1307 non-null   float64
 2   Low     1307 non-null   float64
 3   Close   1307 non-null   float64
 4   Volume  1307 non-null   float64
dtypes: float64(5)
memory usage: 61.3 KB

Ticker: ZVIA
Historical data shape: (1308, 5)
Data Sample (head):
Price       Open  High  Low  Close  Volume
Date                                      
2020-01-02   NaN   NaN  NaN    NaN     NaN
2020-01-03   NaN   NaN  NaN    NaN     NaN
2020-01-06   NaN   NaN  NaN    NaN     NaN
2020-01-07   NaN   NaN  NaN    NaN     NaN
2020-01-08   NaN   NaN  NaN    NaN     NaN
Data Info:
<class 'pandas.core.frame.DataFrame'>
DatetimeIndex: 1308 entries, 2020-01-02 to 2025-03-17
Data columns (total 5 columns):
 #   Column  Non-Null Count  Dtype  
---  ------  --------------  -----  
 0   Open    917 non-null    float64
 1   High    917 non-null    float64
 2   Low     917 non-null    float64
 3   Close   917 non-null    float64
 4   Volume  917 non-null    float64
dtypes: float64(5)
memory usage: 61.3 KB
```


## Latest Price 

```
import yfinance as yf

# Create a Tickers object for multiple tickers
tickers = yf.Tickers("AAPL MSFT GOOGL")

# Access individual ticker info, e.g., current price using fast_info:
print("Apple Price:", tickers.tickers["AAPL"].fast_info["last_price"])
print("Microsoft Price:", tickers.tickers["MSFT"].fast_info["last_price"])
print("Google Price:", tickers.tickers["GOOGL"].fast_info["last_price"])

```

### Output
```
Apple Price: 214.0
Microsoft Price: 388.70001220703125
Google Price: 164.2899932861328
```
---

### Data Summary
Thailand Stock has about 1804 quotes
US Stock has about 5000 quotes

## Ratelimit
It need to has 1 second delay between batch query
and each batch query shoudn't has more than 25-50 quotes in it , you can use parameters used in example it should works.

## Conclusion

This utility provides a structured approach to fetching and processing financial data using **yfinance**. Its design enables:

- Efficient retrieval of all available symbols through batch processing.
- Flexible sample data fetching for quick testing and analysis.
- Detailed logging of both quotes and historical data for in-depth inspection.
- Easy adaptation to different regions (e.g., by changing the query from `'th'` to `'us'`).

Use this code as a foundation for building more advanced financial data analysis tools or integrating it into larger applications.

---