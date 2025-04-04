import datetime
import time
import pandas as pd
import requests
import yfinance as yf
from decimal import Decimal
from utils import safe_convert, chunk_list
import logging
from config import HISTORICAL_START_DATE, REGULAR_TTL, NOT_FOUND_TTL
from cache_storage import latest_cache

logger = logging.getLogger(__name__)

def fetch_yf_data_for_ticker(ticker, start_date=HISTORICAL_START_DATE, end_date=None):
    logger.info(f"Fetching data for stock ticker: {ticker}")
    try:
        data = yf.Ticker(ticker)
        hist = data.history(start=start_date, end=end_date)
        if hist.empty:
            return None, None
        quotes_df = pd.DataFrame([{
            "symbol": ticker,
            "longName": data.info.get("longName"),
            "displayName": data.info.get("displayName"),
            "language": data.info.get("language"),
            "region": data.info.get("region"),
            "quoteType": data.info.get("quoteType"),
            "exchange": data.info.get("exchange"),
            "fullExchangeName": data.info.get("fullExchangeName"),
            "first_trade_date": data.info.get("firstTradeDateEpochUtc")
        }])
        historical_data = {ticker: hist}
        return quotes_df, historical_data
    except Exception as e:
        logger.error(f"Error fetching data for {ticker}: {e}")
        return None, None

def fetch_yf_data(max_tickers_per_request, delay_t, query, start_date=HISTORICAL_START_DATE, end_date=None, sample_size=None):
    logger.info("Starting data fetch from yfinance for stocks...")
    all_quotes = []
    offset = 0
    size = sample_size if sample_size is not None else 250
    if sample_size is not None:
        result = yf.screen(query, offset=0, size=sample_size)
        quotes = result.get("quotes", [])
        all_quotes.extend(quotes)
    else:
        while True:
            result = yf.screen(query, offset=offset, size=size)
            quotes = result.get("quotes", [])
            if not quotes:
                break
            all_quotes.extend(quotes)
            offset += size
    quotes_df = pd.DataFrame(all_quotes)
    symbols = [quote.get("symbol") for quote in all_quotes if quote.get("symbol")]
    historical_data = {}
    for batch_symbols in chunk_list(symbols, max_tickers_per_request):
        tickers_str = " ".join(batch_symbols)
        data = yf.download(tickers=tickers_str, start=start_date, end=end_date, interval="1d", group_by='ticker')
        if isinstance(data.columns, pd.MultiIndex):
            available_tickers = data.columns.get_level_values(0).unique().tolist()
            for ticker in batch_symbols:
                if ticker in available_tickers:
                    historical_data[ticker] = data[ticker]
        else:
            ticker = batch_symbols[0]
            historical_data[ticker] = data
        time.sleep(delay_t)
    return quotes_df, historical_data

def fetch_coingecko_data():
    logger.info("Fetching crypto metadata from CoinGecko...")
    url = "https://api.coingecko.com/api/v3/coins/markets"
    params = {
        "vs_currency": "usd",
        "order": "market_cap_desc",
        "per_page": 250,
        "page": 1,
        "sparkline": "false"
    }
    headers = {"accept": "application/json"}
    try:
        response = requests.get(url, params=params, headers=headers)
        if response.status_code == 200:
            data = response.json()
            logger.info(f"Fetched metadata for {len(data)} cryptocurrencies.")
            return data
        else:
            logger.error("Error fetching crypto metadata: " + response.text)
            return []
    except Exception as e:
        logger.error("Exception fetching crypto metadata: " + str(e))
        return []

def safe_get(url, params=None, max_retries=5):
    for attempt in range(max_retries):
        try:
            response = requests.get(url, params=params, timeout=10)
        except Exception as e:
            logger.error(f"Request error: {e}")
            time.sleep(1)
            continue
        if response.status_code == 200:
            return response
        elif response.status_code in (429, 418):
            retry_after = int(response.headers.get("Retry-After", "1"))
            logger.warning(f"Rate limit hit (HTTP {response.status_code}). Retrying after {retry_after} seconds...")
            time.sleep(retry_after)
        else:
            logger.error(f"Error: HTTP {response.status_code} - {response.text}")
            response.raise_for_status()
    raise Exception("Max retries exceeded for URL: " + url)

def fetch_binance_crypto_data(symbol, start_date, end_date):
    logger.info(f"Fetching Binance historical data for {symbol}...")
    try:
        if start_date:
            start_ts = int(datetime.datetime.strptime(start_date, "%Y-%m-%d").timestamp() * 1000)
        else:
            start_ts = int(datetime.datetime.now().timestamp() * 1000) - (5 * 365 * 24 * 60 * 60 * 1000)
        if end_date:
            end_ts = int(datetime.datetime.strptime(end_date, "%Y-%m-%d").timestamp() * 1000)
        else:
            end_ts = int(datetime.datetime.now().timestamp() * 1000)
    except Exception as e:
        logger.error(f"Error processing dates for symbol {symbol}: {e}")
        return pd.DataFrame()

    limit = 1000
    klines = []
    current_start = start_ts
    url = "https://api.binance.com/api/v3/klines"
    
    while current_start < end_ts:
        try:
            params = {
                "symbol": symbol,
                "interval": "1d",
                "startTime": current_start,
                "endTime": end_ts,
                "limit": limit
            }
            response = safe_get(url, params=params)
            data = response.json()
        except Exception as e:
            logger.error(f"Error fetching data for symbol {symbol} starting at {current_start}: {e}")
            break
        
        if not data:
            break
        
        klines.extend(data)
        last_time = data[-1][0]
        if last_time == current_start:
            break
        current_start = last_time + 1
        time.sleep(0.1)
    
    if not klines:
        return pd.DataFrame()
    
    try:
        df = pd.DataFrame(klines, columns=["open_time", "open", "high", "low", "close", "volume", "close_time",
                                           "quote_asset_volume", "num_trades", "taker_buy_base", "taker_buy_quote", "ignore"])
        df["open_time"] = pd.to_datetime(df["open_time"], unit='ms')
        df.set_index("open_time", inplace=True)
        df = df.astype({"open": "float", "high": "float", "low": "float", "close": "float", "volume": "float"})
    except Exception as e:
        logger.error(f"Error processing DataFrame for symbol {symbol}: {e}")
        return pd.DataFrame()
    
    return df

# Data Source Classes for Latest Price Fetching

class StockDataSource:
    @staticmethod
    def get_latest_price(ticker):
        ds_name = "YFINANCE"
        now = datetime.datetime.now()
        key = (ds_name, ticker)
        if key in latest_cache:
            price, timestamp, expires = latest_cache[key]
            if now < expires:
                return price
            else:
                del latest_cache[key]
        try:
            data = yf.Ticker(ticker)
            price = data.fast_info["last_price"]
            expires = now + datetime.timedelta(minutes=REGULAR_TTL)
            latest_cache[key] = (price, now, expires)
            return price
        except KeyError:
            price = "NOT_FOUND"
            expires = now + datetime.timedelta(minutes=NOT_FOUND_TTL)
            latest_cache[key] = (price, now, expires)
            return price
        except Exception as e:
            logger.error(f"Error fetching latest price for stock {ticker}: {e}")
            return None

    @staticmethod
    def refresh_latest_prices(tickers):
        prices = {}
        tickers_str = " ".join(tickers)
        data = yf.Tickers(tickers_str)
        for ticker in tickers:
            try:
                price = data.tickers[ticker].fast_info["last_price"]
                prices[ticker] = price
            except KeyError:
                prices[ticker] = "NOT_FOUND"
            except Exception as e:
                logger.error(f"Error fetching latest price for stock {ticker}: {e}")
        return prices

class CryptoDataSource:
    BASE_URL = "https://api.binance.com/api/v3"

    @staticmethod
    def get_all_latest_prices():
        url = f"{CryptoDataSource.BASE_URL}/ticker/price"
        try:
            response = requests.get(url)
            if response.status_code == 200:
                data = response.json()
                prices = {}
                now = datetime.datetime.now()
                for item in data:
                    symbol = item["symbol"]
                    price = float(item["price"])
                    key = ("BINANCE", symbol)
                    expires = now + datetime.timedelta(minutes=REGULAR_TTL)
                    latest_cache[key] = (price, now, expires)
                    prices[symbol] = price
                return prices
            return {}
        except Exception as e:
            logger.error("Error fetching crypto prices: " + str(e))
            return {}

    @staticmethod
    def get_latest_price(ticker):
        ds_name = "BINANCE"
        now = datetime.datetime.now()
        key = (ds_name, ticker)
        if key in latest_cache:
            price, timestamp, expires = latest_cache[key]
            if now < expires:
                return price
            else:
                del latest_cache[key]
        url = f"{CryptoDataSource.BASE_URL}/ticker/price"
        params = {"symbol": ticker}
        try:
            response = requests.get(url, params=params)
            if response.status_code == 200:
                data = response.json()
                price = float(data["price"])
                expires = now + datetime.timedelta(minutes=REGULAR_TTL)
                latest_cache[key] = (price, now, expires)
                return price
            else:
                price = "NOT_FOUND"
                expires = now + datetime.timedelta(minutes=NOT_FOUND_TTL)
                latest_cache[key] = (price, now, expires)
                return "NOT_FOUND"
        except Exception as e:
            logger.error(f"Error fetching latest price for crypto {ticker}: {e}")
            return None

# Currency Data Fetching Functions

def fetch_fx_realtime(from_currency, to_currency="USD"):
    from config import ALPHAVANTAGE_API_KEY
    url = "https://www.alphavantage.co/query"
    params = {
        "function": "CURRENCY_EXCHANGE_RATE",
        "from_currency": from_currency,
        "to_currency": to_currency,
        "apikey": ALPHAVANTAGE_API_KEY
    }
    try:
        response = requests.get(url, params=params)
        if response.status_code == 200:
            data = response.json()
            rate_info = data.get("Realtime Currency Exchange Rate", {})
            rate = rate_info.get("5. Exchange Rate")
            if rate:
                return float(rate)
        return None
    except Exception as e:
        logger.error(f"Error fetching realtime FX data for {from_currency}/{to_currency}: {e}")
        return None

def fetch_fx_daily_data(from_currency, to_currency="USD", outputsize="compact"):
    from config import ALPHAVANTAGE_API_KEY
    url = "https://www.alphavantage.co/query"
    params = {
        "function": "FX_DAILY",
        "from_symbol": from_currency,
        "to_symbol": to_currency,
        "outputsize": outputsize,
        "apikey": ALPHAVANTAGE_API_KEY
    }
    try:
        response = requests.get(url, params=params)
        if response.status_code == 200:
            data = response.json()
            time_series = data.get("Time Series FX (Daily)", {})
            if time_series:
                df = pd.DataFrame.from_dict(time_series, orient='index')
                df.index = pd.to_datetime(df.index)
                df = df.rename(columns={
                    "1. open": "Open",
                    "2. high": "High",
                    "3. low": "Low",
                    "4. close": "Close"
                })
                df = df.astype(float)
                return df
        return None
    except Exception as e:
        logger.error(f"Error fetching FX daily data for {from_currency}/{to_currency}: {e}")
        return None

class CurrencyDataSource:
    @staticmethod
    def get_latest_price(currency_code):
        ds_name = "ALPHAVANTAGE"
        now = datetime.datetime.now()
        key = (ds_name, currency_code.upper())
        if key in latest_cache:
            price, timestamp, expires = latest_cache[key]
            if now < expires:
                return price
            else:
                del latest_cache[key]
        if currency_code.upper() == "USD":
            price = 1.0
            expires = now + datetime.timedelta(minutes=REGULAR_TTL)
            latest_cache[key] = (price, now, expires)
            return price
        price = fetch_fx_realtime(currency_code, "USD")
        if price is not None:
            expires = now + datetime.timedelta(minutes=REGULAR_TTL)
            latest_cache[key] = (price, now, expires)
            return price
        else:
            price = "NOT_FOUND"
            expires = now + datetime.timedelta(minutes=NOT_FOUND_TTL)
            latest_cache[key] = (price, now, expires)
            return "NOT_FOUND"

    @staticmethod
    def refresh_latest_prices(currency_codes):
        prices = {}
        for code in currency_codes:
            price = CurrencyDataSource.get_latest_price(code)
            prices[code] = price if price is not None else "NOT_FOUND"
        return prices
