import datetime
import time
import pandas as pd
import requests
import yfinance as yf
from decimal import Decimal
from utils import safe_convert, chunk_list
import logging

logger = logging.getLogger(__name__)

def fetch_yf_data_for_ticker(ticker, start_date="2020-01-01", end_date=None):
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

def fetch_yf_data(max_tickers_per_request, delay_t, query, start_date="2020-01-01", end_date=None, sample_size=None):
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
        try:
            data = yf.Ticker(ticker)
            return data.fast_info["last_price"]
        except KeyError:
            return "NOT_FOUND"
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
                return { item["symbol"]: float(item["price"]) for item in data }
            return {}
        except Exception as e:
            logger.error("Error fetching crypto prices: " + str(e))
            return {}

    @staticmethod
    def get_latest_price(ticker):
        url = f"{CryptoDataSource.BASE_URL}/ticker/price"
        params = {"symbol": ticker}
        try:
            response = requests.get(url, params=params)
            if response.status_code == 200:
                data = response.json()
                return float(data["price"])
            return "NOT_FOUND"
        except Exception as e:
            logger.error(f"Error fetching latest price for crypto {ticker}: {e}")
            return None