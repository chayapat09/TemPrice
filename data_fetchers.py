import datetime
import time
import pandas as pd
import requests
import yfinance as yf
from decimal import Decimal
from utils import safe_convert, chunk_list
import logging
from config import CURRENCY_CACHE_TTL, HISTORICAL_START_DATE, REGULAR_TTL, NOT_FOUND_TTL # OXR_APP_ID imported in methods
from cache_storage import latest_cache
from dataclasses import dataclass # Added
from typing import Dict, Optional # Added

logger = logging.getLogger(__name__)

# --- Dataclass for OpenExchangeRates DTO ---
@dataclass
class ExchangeRatesDTO:
    base: str                 # e.g. "USD"
    rates: Dict[str, float]   # e.g. {"EUR":0.9234, "THB":35.4123, ...}
    timestamp: datetime.datetime       # when the rates were last updated (made specific)

# --- Fetch function for OpenExchangeRates ---
def fetch_all_usd_rates_oxr(app_id: str) -> Optional[ExchangeRatesDTO]:
    """
    Calls OpenExchangeRates 'latest' endpoint for USD->ALL
    and returns an ExchangeRatesDTO containing every currency rate.
    Returns None on failure.
    """
    url = "https://openexchangerates.org/api/latest.json"
    params = {"app_id": app_id}
    logger.info(f"Fetching all USD rates from OpenExchangeRates with app_id ending in ...{app_id[-4:] if app_id else 'N/A'}")
    try:
        resp = requests.get(url, params=params, timeout=10) # Increased timeout slightly
        resp.raise_for_status()
        data = resp.json()

        if data.get("base") != "USD":
            logger.error(f"OpenExchangeRates API did not return USD as base. Base was: {data.get('base')}")
            return None
        
        # Ensure rates is a dictionary
        rates_data = data.get("rates")
        if not isinstance(rates_data, dict):
            logger.error(f"OpenExchangeRates API 'rates' field is not a dictionary. Type: {type(rates_data)}")
            return None

        return ExchangeRatesDTO(
            base=data["base"],
            rates=rates_data,
            timestamp=datetime.datetime.fromtimestamp(data["timestamp"]) # Consider timezone awareness if critical
        )
    except requests.exceptions.HTTPError as http_err:
        logger.error(f"HTTP error fetching from OpenExchangeRates: {http_err} - Response: {resp.text if 'resp' in locals() else 'N/A'}")
        return None
    except requests.exceptions.RequestException as e:
        logger.error(f"Request error fetching from OpenExchangeRates: {e}")
        return None
    except (KeyError, TypeError, ValueError) as e: # Broader exception for data parsing
        logger.error(f"Error parsing OpenExchangeRates response: {e}")
        return None
    
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
        result = yf.screener.screen(query, offset=0, size=sample_size)
        quotes = result.get("quotes", [])
        all_quotes.extend(quotes)
    else:
        while True:
            result = yf.screener.screen(query, offset=offset, size=size)
            quotes = result.get("quotes", [])
            if not quotes:
                break
            all_quotes.extend(quotes)
            offset += size
    quotes_df = pd.DataFrame(all_quotes)
    if not quotes_df.empty and "symbol" in quotes_df.columns:
        symbols = quotes_df["symbol"].dropna().tolist()
    else:
        logger.warning("No symbol data returned from yfinance screener.")
        return quotes_df, {}
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
    DS_NAME = "YFINANCE"
    @staticmethod
    def get_latest_price(ticker):
        ds_name = StockDataSource.DS_NAME
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
    DS_NAME = "BINANCE"
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
    OXR_DS_NAME = "OPENEXCHANGERATES" # For OpenExchangeRates real-time data
    ALPHAVANTAGE_DS_NAME = "ALPHAVANTAGE" # For AlphaVantage historical data

    @staticmethod
    def get_latest_price(currency_pair_ticker: str): # e.g., "EURUSD", "THBUSD"
        """
        Fetches the latest price for a currency pair like EURUSD or THBUSD.
        Uses OpenExchangeRates data from cache.
        The currency_pair_ticker is in <QUOTE><BASE> format (e.g., EURUSD means 1 EUR = X USD).
        """
        now = datetime.datetime.now()
        # Cache key is based on OXR as the source for these latest prices
        key = (CurrencyDataSource.OXR_DS_NAME, currency_pair_ticker.upper())
        
        cached_item = latest_cache.get(key)
        if cached_item:
            price, timestamp, expires = cached_item
            if now < expires:
                return price
            else:
                logger.debug(f"Currency cache expired for {key} (OXR), removing.")
                del latest_cache[key]
        
        # If not in cache or expired, it means refresh_latest_prices should have populated it.
        # This method primarily reads from the cache.
        logger.warning(f"Latest price for {currency_pair_ticker} not found in OXR cache. Relies on periodic refresh job.")
        
        # Handle USDUSD explicitly as it's a common case and won't be in OXR's 'rates' for other currencies.
        if currency_pair_ticker.upper() == "USDUSD":
            price = 1.0
            # Cache USDUSD for a longer period as it's constant
            expires = now + datetime.timedelta(days=7) # Cache for a week
            latest_cache[key] = (price, now, expires)
            return price

        # For other pairs, if not found by refresh job, mark as NOT_FOUND.
        # The refresh job is responsible for fetching from OXR and populating.
        price_to_cache = "NOT_FOUND"
        expires = now + datetime.timedelta(minutes=NOT_FOUND_TTL) # Cache "NOT_FOUND"
        latest_cache[key] = (price_to_cache, now, expires)
        return price_to_cache

    @staticmethod
    def refresh_latest_prices():
        """
        Fetches all USD-based rates from OpenExchangeRates, inverts them to <QUOTE>USD format,
        and updates the latest_cache. This is the primary method for populating real-time currency cache.
        Returns a dictionary of tickers and their successfully updated prices.
        """
        from config import OXR_APP_ID # Import here to ensure fresh config access
        
        if not OXR_APP_ID or ("e175a1fe5ec843eea664685474cd52e7" in OXR_APP_ID and "YOUR_APP_ID" in OXR_APP_ID): # Basic check for placeholder or default example key
             logger.warning("OpenExchangeRates OXR_APP_ID is not configured or is a placeholder/example. Skipping currency refresh from OXR.")
             return {}

        oxr_dto = fetch_all_usd_rates_oxr(OXR_APP_ID)
        prices_updated_map = {}
        now = datetime.datetime.now()

        if oxr_dto and oxr_dto.base == "USD":
            logger.info(f"Fetched {len(oxr_dto.rates)} rates from OpenExchangeRates (base {oxr_dto.base}) at {oxr_dto.timestamp}.")
            
            # Handle USD against USD (e.g., USDUSD)
            usdusd_ticker = "USDUSD"
            usdusd_key = (CurrencyDataSource.OXR_DS_NAME, usdusd_ticker)
            # Cache USDUSD for a long time as it's fixed at 1.0
            usdusd_expires = now + datetime.timedelta(days=30) 
            latest_cache[usdusd_key] = (1.0, now, usdusd_expires)
            prices_updated_map[usdusd_ticker] = 1.0
            logger.debug(f"Cached {usdusd_ticker}: 1.0")

            for quote_currency_code, usd_to_quote_rate in oxr_dto.rates.items():
                if quote_currency_code.upper() == "USD": # USD itself, rate is 1 to USD
                    continue # Already handled by USDUSD

                if usd_to_quote_rate is None or not isinstance(usd_to_quote_rate, (int, float)):
                    logger.warning(f"Invalid rate type for USD{quote_currency_code} from OXR: {usd_to_quote_rate}. Skipping.")
                    continue
                if usd_to_quote_rate <= 0: # Rate must be positive for inversion
                    logger.warning(f"Non-positive rate for USD{quote_currency_code} from OXR: {usd_to_quote_rate}. Cannot invert, skipping.")
                    continue

                # OXR provides: 1 USD = X QUOTE (e.g., USDTHB = 35.0)
                # We need to store: 1 QUOTE = Y USD (e.g., THBUSD = 1/35.0)
                try:
                    quote_to_usd_rate = 1.0 / usd_to_quote_rate
                except ZeroDivisionError: # Should be caught by previous check, but defensively
                    logger.error(f"ZeroDivisionError for USD{quote_currency_code} rate {usd_to_quote_rate}. Skipping.")
                    continue
                
                # Internal ticker convention: <QUOTE_CURRENCY>USD (e.g., THBUSD, EURUSD)
                internal_pair_ticker = f"{quote_currency_code.upper()}USD"
                cache_key = (CurrencyDataSource.OXR_DS_NAME, internal_pair_ticker)
                
                # Standard TTL for fetched rates
                rate_expires = now + datetime.timedelta(minutes=CURRENCY_CACHE_TTL)
                
                latest_cache[cache_key] = (quote_to_usd_rate, now, rate_expires)
                prices_updated_map[internal_pair_ticker] = quote_to_usd_rate
                logger.debug(f"Cached {internal_pair_ticker}: {quote_to_usd_rate:.6f} (from OXR USD{quote_currency_code}={usd_to_quote_rate})")
        else:
            logger.error("Failed to fetch or validate data from OpenExchangeRates for currency refresh.")
            if oxr_dto and oxr_dto.base != "USD": # Log if base is not USD
                 logger.error(f"OXR base currency was {oxr_dto.base}, expected USD.")
        
        return prices_updated_map