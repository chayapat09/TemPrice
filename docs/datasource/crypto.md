# API NEEDED.
1. List All Symbol in Provider (Market)
2. OHLC(V) API for Ticker (Symbol)
3. Latest(Realtime) Price Data (For All Symbol / Specific symbol)


## Coingeko Limit
Total Monthly API Calls
0 / 10,000
Remaining monthly API Calls
10,000
Rate Limit - Request Per Minute
30

## APIs
### Coins List (ID Map)
get
https://api.coingecko.com/api/v3/coins/list
This endpoint allows you to query all the supported coins on CoinGecko with coins ID, name and symbol

You may use this endpoint to query the list of coins with coin ID for other endpoints that contain params like id or ids (coin ID).


There is no pagination required for this endpoint.
Access to inactive coins via the Public API (Demo plan) is restricted. To access them, please subscribe to one of our paid plans to obtain a Pro-API key.

### Request
```
import requests

url = "https://api.coingecko.com/api/v3/coins/list"

headers = {
    "accept": "application/json",
    "x-cg-demo-api-key": "xxx"
}

response = requests.get(url, headers=headers)

print(response.text)
```

### Response (Example)
```
[
  {
    "id": "0chain",
    "symbol": "zcn",
    "name": "Zus",
    "platforms": {
      "ethereum": "0xb9ef770b6a5e12e45983c5d80545258aa38f3b78",
      "polygon-pos": "0x8bb30e0e67b11b978a5040144c410e1ccddcba30"
    }
  },
  {
    "id": "01coin",
    "symbol": "zoc",
    "name": "01coin",
    "platforms": {}
  }
]
```


```
Coins List with Market Data
get
https://api.coingecko.com/api/v3/coins/markets
This endpoint allows you to query all the supported coins with price, market cap, volume and market related data

👍
Tips

You may specify the coins’ IDs in ids parameter if you want to retrieve market data for specific coins only instead of the whole list.
You may also provide value in category to filter the responses based on coin's category.
You can use per_page and page values to control the number of results per page and specify which page of results you want to display in the responses.
📘
Notes

If you provide values for both category and ids parameters, the category parameter will be prioritized over the ids parameter.
Cache/Update Frequency:
Every 60 seconds for Public API.
every 45 seconds for Pro API (Analyst, Lite, Pro, Enterprise).
Query Params
vs_currency
string
required
target currency of coins and market data
*refers to /simple/supported_vs_currencies.

usd
ids
string
coins' IDs, comma-separated if querying more than 1 coin.
*refers to /coins/list.

category
string
filter based on coins' category
*refers to /coins/categories/list.

order
string
sort result by field, default: market_cap_desc


per_page
integer
total results per page, default: 100
Valid values: 1...250

250
page
integer
page through results, default: 1

1
sparkline
boolean
include sparkline 7 days data, default: false


price_change_percentage
string
include price change percentage timeframe, comma-separated if query more than 1 price change percentage timeframe
Valid values: 1h, 24h, 7d, 14d, 30d, 200d, 1y

locale
string
language background, default: en


precision
string
decimal place for currency price value


full
Response

200
List all coins with market data

Response body
object
id
string
coin ID

symbol
string
coin symbol

name
string
coin name

image
string
coin image url

current_price
number
coin current price in currency

market_cap
number
coin market cap in currency

market_cap_rank
number
coin rank by market cap

fully_diluted_valuation
number
coin fully diluted valuation (fdv) in currency

total_volume
number
coin total trading volume in currency

high_24h
number
coin 24hr price high in currency

low_24h
number
coin 24hr price low in currency

price_change_24h
number
coin 24hr price change in currency

price_change_percentage_24h
number
coin 24hr price change in percentage

market_cap_change_24h
number
coin 24hr market cap change in currency

market_cap_change_percentage_24h
number
coin 24hr market cap change in percentage

circulating_supply
number
coin circulating supply

total_supply
number
coin total supply

max_supply
number
coin max supply

ath
number
coin all time high (ath) in currency

ath_change_percentage
number
coin all time high (ath) change in percentage

ath_date
date-time
coin all time high (ath) date

atl
number
coin all time low (atl) in currency

atl_change_percentage
number
coin all time low (atl) change in percentage

atl_date
date-time
coin all time low (atl) date

roi
string
last_updated
date-time
coin last updated timestamp

price_change_percentage_1h
number
coin 1h price change in percentage

sparkline_in_7d
object
coin price sparkline in 7 days

price
array of numbers

Request example
import requests

url = "https://api.coingecko.com/api/v3/coins/markets?vs_currency=usd&per_page=250&page=1&precision=full"

headers = {
    "accept": "application/json",
    "x-cg-demo-api-key": "xxx"
}

response = requests.get(url, headers=headers)

print(response.text)

Reponse Example
[
  {
    "id": "bitcoin",
    "symbol": "btc",
    "name": "Bitcoin",
    "image": "https://assets.coingecko.com/coins/images/1/large/bitcoin.png?1696501400",
    "current_price": 70187,
    "market_cap": 1381651251183,
    "market_cap_rank": 1,
    "fully_diluted_valuation": 1474623675796,
    "total_volume": 20154184933,
    "high_24h": 70215,
    "low_24h": 68060,
    "price_change_24h": 2126.88,
    "price_change_percentage_24h": 3.12502,
    "market_cap_change_24h": 44287678051,
    "market_cap_change_percentage_24h": 3.31157,
    "circulating_supply": 19675987,
    "total_supply": 21000000,
    "max_supply": 21000000,
    "ath": 73738,
    "ath_change_percentage": -4.77063,
    "ath_date": "2024-03-14T07:10:36.635Z",
    "atl": 67.81,
    "atl_change_percentage": 103455.83335,
    "atl_date": "2013-07-06T00:00:00.000Z",
    "roi": null,
    "last_updated": "2024-04-07T16:49:31.736Z"
  }
]
```


Binance API

use to populated data for OHLC(V) historical Data
Example code for related API
```
#!/usr/bin/env python3
import argparse
import requests
import time
import datetime
import sys

BASE_URL = "https://api.binance.com"

def safe_get(url, params=None, max_retries=5):
    """
    Makes a GET request using the requests library while handling rate limits.
    If a 429 (Too Many Requests) or 418 (IP Ban) response is encountered,
    it reads the Retry-After header (or defaults to 1 second) and retries after waiting.
    
    Parameters:
      url (str): The endpoint URL.
      params (dict): Optional query parameters.
      max_retries (int): Maximum number of retries before failing.
    
    Returns:
      Response object if successful.
    
    Raises:
      Exception if maximum retries are exceeded.
    """
    for attempt in range(max_retries):
        try:
            response = requests.get(url, params=params, timeout=10)
        except Exception as e:
            print(f"Request error: {e}")
            time.sleep(1)
            continue

        if response.status_code == 200:
            # Optionally, print out the used weight header if available.
            used_weight = response.headers.get("X-MBX-USED-WEIGHT-1m")
            if used_weight:
                print(f"[DEBUG] Used weight (1m): {used_weight}")
            return response
        elif response.status_code in (429, 418):
            retry_after = int(response.headers.get("Retry-After", "1"))
            print(f"Rate limit hit (HTTP {response.status_code}). Retrying after {retry_after} seconds...")
            time.sleep(retry_after)
        else:
            print(f"Error: HTTP {response.status_code} - {response.text}")
            response.raise_for_status()
    raise Exception("Max retries exceeded for URL: " + url)

def get_exchange_info():
    """
    Retrieves exchange information including all symbols and their metadata.
    
    Returns:
      list: A list of dictionaries, each representing a symbol and its metadata.
    """
    url = BASE_URL + "/api/v3/exchangeInfo"
    response = safe_get(url)
    data = response.json()
    return data.get("symbols", [])

def get_top_100_tickers():
    """
    Retrieves 24-hour ticker data for all symbols and returns the top 100
    sorted by quoteVolume (highest first).
    
    Returns:
      list: A list of the top 100 ticker dictionaries.
    """
    url = BASE_URL + "/api/v3/ticker/24hr"
    response = safe_get(url)
    data = response.json()
    # Sort by quoteVolume (converted from string to float) descending.
    sorted_data = sorted(data, key=lambda x: float(x.get("quoteVolume", 0)), reverse=True)
    top100 = sorted_data[:100]
    return top100

def get_historical_klines(symbol, interval, start_time, end_time):
    """
    Retrieves historical candlestick (kline) data for a given symbol over a specified period.
    
    Parameters:
      symbol (str): Trading pair symbol (e.g., "BTCUSDT").
      interval (str): Kline interval (e.g., "1d" for daily).
      start_time (int): Start time in milliseconds (epoch ms).
      end_time (int): End time in milliseconds (epoch ms).
    
    Returns:
      list: A list of klines where each kline is a list containing 12 elements:
            [Open time, Open, High, Low, Close, Volume, Close time, Quote asset volume,
             Number of trades, Taker buy base asset volume, Taker buy quote asset volume, Ignore]
    """
    url = BASE_URL + "/api/v3/klines"
    limit = 1000  # maximum number of klines per request
    klines = []
    current_start = start_time
    while current_start < end_time:
        params = {
            "symbol": symbol,
            "interval": interval,
            "startTime": current_start,
            "endTime": end_time,
            "limit": limit
        }
        response = safe_get(url, params=params)
        data = response.json()
        if not data:
            break
        klines.extend(data)
        last_time = data[-1][0]
        if last_time == current_start:
            break
        current_start = last_time + 1
        time.sleep(0.1)
    return klines

def get_current_prices_for_symbols(symbols):
    """
    Retrieves the current prices for a given list of symbols.
    
    This function calls the /api/v3/ticker/price endpoint without a specific symbol parameter
    so that it receives price data for all symbols. It then filters the results to include only
    the symbols provided in the input list and returns a list of dictionaries exactly matching the 
    API structure (each with "symbol" and "price").
    
    Parameters:
      symbols (list): A list of symbol strings (e.g., ["BTCUSDT", "ETHUSDT"]).
    
    Returns:
      list: A list of dictionaries in the same format as the API response, each with keys:
            - "symbol": the trading pair symbol.
            - "price": the current price as a string.
    """
    url = BASE_URL + "/api/v3/ticker/price"
    response = safe_get(url)
    data = response.json()  # Data is a list of dictionaries with keys "symbol" and "price"
    # Filter the list to include only entries whose "symbol" is in the input list.
    filtered = [entry for entry in data if entry.get("symbol") in symbols]
    return filtered

def ms_to_date(ms):
    """Converts epoch milliseconds to a human-readable date string."""
    return datetime.datetime.fromtimestamp(ms / 1000.0).strftime("%Y-%m-%d %H:%M:%S")

def print_symbols(symbols):
    print("Listing all symbols with metadata:")
    for s in symbols:
        print(f"{s['symbol']}: status={s['status']}, base={s['baseAsset']}, quote={s['quoteAsset']}")

def print_tickers(tickers):
    print("Top 100 coins by 24hr quote volume:")
    for t in tickers:
        print(f"{t['symbol']}: price={t['lastPrice']}, quoteVolume={t['quoteVolume']}")

def print_price_list(price_list):
    print("Current prices for provided symbols:")
    for entry in price_list:
        print(f"{entry['symbol']}: {entry['price']}")

def main():
    parser = argparse.ArgumentParser(description="Binance API Data Retrieval Script")
    parser.add_argument("--action", type=str, required=True,
                        choices=["list_symbols", "top100", "historical", "prices"],
                        help="Action to perform: 'list_symbols' to list all symbols; 'top100' to fetch realtime top 100 tickers; 'historical' to fetch 5-year OHLC data; 'prices' to get current prices for a list of symbols")
    parser.add_argument("--symbol", type=str, help="Trading pair symbol for historical data (e.g. BTCUSDT)")
    parser.add_argument("--symbols", type=str, help="Comma-separated list of symbols to fetch current prices for (e.g. BTCUSDT,ETHUSDT)")
    args = parser.parse_args()

    if args.action == "list_symbols":
        symbols = get_exchange_info()
        print(f"Found {len(symbols)} symbols on Binance.")
        print_symbols(symbols)
    elif args.action == "top100":
        print("Starting realtime update of top 100 coins (updates every 5 minutes). Press Ctrl+C to stop.")
        try:
            while True:
                top100 = get_top_100_tickers()
                print_tickers(top100)
                print("Sleeping for 5 minutes until next update...")
                time.sleep(300)
        except KeyboardInterrupt:
            print("Realtime update stopped.")
            sys.exit(0)
    elif args.action == "historical":
        if not args.symbol:
            print("Error: Please provide --symbol for historical data (e.g. --symbol BTCUSDT)")
            sys.exit(1)
        end_time = int(time.time() * 1000)
        five_years_ms = 5 * 365 * 24 * 60 * 60 * 1000
        start_time = end_time - five_years_ms
        print(f"Fetching daily OHLC data for {args.symbol} from {ms_to_date(start_time)} to {ms_to_date(end_time)} ...")
        klines = get_historical_klines(args.symbol, "1d", start_time, end_time)
        print(f"Retrieved {len(klines)} klines for {args.symbol}.")
        for k in klines:
            open_time = ms_to_date(k[0])
            o, h, l, c, v = k[1], k[2], k[3], k[4], k[5]
            print(f"{open_time}: O={o}, H={h}, L={l}, C={c}, V={v}")
    elif args.action == "prices":
        if not args.symbols:
            print("Error: Please provide --symbols for current price lookup (e.g. --symbols BTCUSDT,ETHUSDT)")
            sys.exit(1)
        symbols_list = [s.strip() for s in args.symbols.split(",")]
        prices = get_current_prices_for_symbols(symbols_list)
        print_price_list(prices)
    else:
        print("Invalid action specified.")

if __name__ == "__main__":
    main()

```

1. List All Symbols in Provider (Market)
Endpoint: GET /api/v3/exchangeInfo
Purpose: Returns current exchange trading rules and information on all available trading symbols.
Key Details:
Response Structure:
A JSON object with fields including:
timezone – typically "UTC".
serverTime – current Binance server time.
rateLimits – an array defining various rate limits.
exchangeFilters – an array of filters applied at the exchange level.
symbols – an array of symbol objects. Each symbol object contains details such as:
symbol (e.g. "ETHBTC")
status (e.g. "TRADING")
baseAsset and quoteAsset
Precision settings, allowed order types, filters (e.g. PRICE_FILTER), and permissions.
Example Usage:
A client can call this endpoint (without any parameters) to retrieve the list of all trading pairs and their details.
2. OHLC(V) API for Ticker (Symbol)
Endpoint: GET /api/v3/klines
Purpose: Provides candlestick (kline) data for a specific symbol, which includes Open, High, Low, Close (OHLC) values and volume information.
Key Details:
Required Parameter:
symbol: The trading pair (e.g. "BTCUSDT").
interval: The time interval for each candlestick (e.g. "1m", "1h", "1d", etc.).
Optional Parameters:
startTime and endTime for defining the time range.
limit to restrict the number of returned bars (default is usually set, maximum can be up to 5000).
timeZone (optional, defaults to UTC).
Response Structure:
Returns an array of arrays where each inner array represents a candlestick bar containing:
Open time (in milliseconds)
Open price (string)
High price (string)
Low price (string)
Close price (string)
Volume (string)
Close time (in milliseconds)
Quote asset volume (string)
Number of trades (integer)
Taker buy base asset volume (string)
Taker buy quote asset volume (string)
Ignore (string; typically unused)
Example Usage:
A request to this endpoint with parameters symbol=BTCUSDT and interval=1h will return hourly candlestick data for Bitcoin trading against USDT.
3. Latest (Realtime) Price Data (For All Symbol / Specific symbol)
Endpoint: GET /api/v3/ticker/price
Purpose: Retrieves the latest price for a specific symbol or all symbols.
Key Details:
Parameters:
symbol (optional): When provided, returns the price for that specific symbol.
Omitting the symbol parameter returns an array containing the latest price information for all trading pairs.
Response Structure:
Single Symbol:
A JSON object with:
symbol (e.g. "BTCUSDT")
price (e.g. "31000.00000000")
Multiple Symbols:
An array of objects, each with the same structure as above.
Example Usage:
To get the current price for all symbols, simply call the endpoint without any symbol parameter.
To get the price for a particular pair (e.g. BTCUSDT), include symbol=BTCUSDT in the query string.
These endpoints provide the core market data functionalities from the Binance Public Spot API. They are used for listing available symbols, obtaining historical OHLC data for charting, and fetching up-to-date price information either for a single symbol or across the entire market.