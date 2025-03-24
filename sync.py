import datetime
import time
import pandas as pd
from decimal import Decimal
from models import Asset, StockAsset, CryptoAsset, CurrencyAsset, DataSource, AssetQuote, AssetOHLCV, DeltaSyncState, Session
from data_fetchers import fetch_yf_data_for_ticker, fetch_yf_data, fetch_coingecko_data, fetch_binance_crypto_data
from utils import safe_convert
from sqlalchemy.exc import SQLAlchemyError
import logging
from config import REGULAR_TTL

from cache_storage import latest_cache  # Import from the new cache module

logger = logging.getLogger(__name__)

def update_stock_asset_and_quote(quotes_df, historical_data, upsert=False):
    session = Session()
    try:
        data_source = session.query(DataSource).filter_by(name="yFinance").first()
        if not data_source:
            data_source = DataSource(name="yFinance", description="Yahoo Finance data source")
            session.add(data_source)
            session.commit()

        for idx, row in quotes_df.iterrows():
            ticker = row.get("symbol")
            if not ticker:
                continue
            name = row.get("longName") or row.get("displayName") or ticker
            language = row.get("language")
            region = row.get("region")
            exchange = row.get("exchange")
            full_exchange_name = row.get("fullExchangeName")
            first_trade = safe_convert(row.get("first_trade_date"), lambda x: datetime.datetime.fromtimestamp(x / 1000).date()) if row.get("first_trade_date") else None

            asset = session.query(Asset).filter_by(asset_type="STOCK", symbol=ticker).first()
            if not asset:
                asset = StockAsset(asset_type="STOCK", symbol=ticker, name=name, language=language,
                                   region=region, exchange=exchange, full_exchange_name=full_exchange_name,
                                   first_trade_date=first_trade, source_asset_key=ticker)
                session.add(asset)
            else:
                asset.name = name
                asset.source_asset_key = ticker
                if hasattr(asset, "language"):
                    asset.language = language
                    asset.region = region
                    asset.exchange = exchange
                    asset.full_exchange_name = full_exchange_name
                    asset.first_trade_date = first_trade

            exchange_currency_map = {
                "NMS": "USD",
                "NYQ": "USD",
                "SET": "THB"
            }
            quote_currency = exchange_currency_map.get(exchange, "USD")
            currency_asset = session.query(CurrencyAsset).filter_by(asset_type="CURRENCY", symbol=quote_currency).first()
            if not currency_asset:
                currency_asset = CurrencyAsset(asset_type="CURRENCY", symbol=quote_currency, name=quote_currency, source_asset_key=quote_currency)
                session.add(currency_asset)
            
            composite_ticker = ticker + quote_currency
            asset_quote = session.query(AssetQuote).filter_by(ticker=composite_ticker, data_source_id=data_source.id).first()
            if not asset_quote:
                asset_quote = AssetQuote(
                    from_asset_type="STOCK",
                    from_asset_symbol=ticker,
                    to_asset_type="CURRENCY",
                    to_asset_symbol=quote_currency,
                    data_source_id=data_source.id,
                    ticker=composite_ticker,
                    source_ticker=ticker
                )
                session.add(asset_quote)
            else:
                asset_quote.source_ticker = ticker

            if ticker in historical_data and historical_data[ticker] is not None:
                df = historical_data[ticker]
                for date, row_data in df.iterrows():
                    price_date = date if isinstance(date, datetime.datetime) else datetime.datetime.combine(date, datetime.time())
                    exists = session.query(AssetOHLCV).filter_by(asset_quote_id=asset_quote.id, price_date=price_date).first()
                    if exists:
                        if upsert:
                            exists.open_price = safe_convert(row_data.get("Open"), float)
                            exists.high_price = safe_convert(row_data.get("High"), float)
                            exists.low_price = safe_convert(row_data.get("Low"), float)
                            exists.close_price = safe_convert(row_data.get("Close"), float)
                            exists.volume = safe_convert(row_data.get("Volume"), Decimal)
                    else:
                        ohlcv = AssetOHLCV(
                            asset_quote=asset_quote,
                            price_date=price_date,
                            open_price=safe_convert(row_data.get("Open"), float),
                            high_price=safe_convert(row_data.get("High"), float),
                            low_price=safe_convert(row_data.get("Low"), float),
                            close_price=safe_convert(row_data.get("Close"), float),
                            volume=safe_convert(row_data.get("Volume"), Decimal)
                        )
                        session.add(ohlcv)
        session.commit()
    except SQLAlchemyError as e:
        session.rollback()
        logger.error(f"Error updating stock assets and quotes: {e}")
        raise
    finally:
        session.close()

def update_crypto_asset_and_quote(crypto_data, historical_data, upsert=False):
    session = Session()
    try:
        data_source = session.query(DataSource).filter_by(name="Binance").first()
        if not data_source:
            data_source = DataSource(name="Binance", description="Binance API data source")
            session.add(data_source)
            session.commit()

        for coin in crypto_data:
            coin_id = coin.get("id")
            coin_symbol = coin.get("symbol").upper()
            name = coin.get("name")
            image = coin.get("image")
            ath = safe_convert(coin.get("ath"), float)
            ath_date = pd.to_datetime(coin.get("ath_date")) if coin.get("ath_date") else None
            atl = safe_convert(coin.get("atl"), float)
            atl_date = pd.to_datetime(coin.get("atl_date")) if coin.get("atl_date") else None
            total_supply = safe_convert(coin.get("total_supply"), int)
            max_supply = safe_convert(coin.get("max_supply"), int)
            
            asset = session.query(Asset).filter_by(asset_type="CRYPTO", symbol=coin_symbol).first()
            if not asset:
                asset = CryptoAsset(asset_type="CRYPTO", symbol=coin_symbol, name=name, image=image,
                                    ath=ath, ath_date=ath_date, atl=atl, atl_date=atl_date,
                                    total_supply=total_supply, max_supply=max_supply,
                                    source_asset_key=coin_id)
                session.add(asset)
            else:
                asset.name = name
                asset.source_asset_key = coin_id
                if hasattr(asset, "image"):
                    asset.image = image
                    asset.ath = ath
                    asset.ath_date = ath_date
                    asset.atl = atl
                    asset.atl_date = atl_date
                    asset.total_supply = total_supply
                    asset.max_supply = max_supply
            
            quote_currency = "USDT"
            currency_asset = session.query(CurrencyAsset).filter_by(asset_type="CURRENCY", symbol=quote_currency).first()
            if not currency_asset:
                currency_asset = CurrencyAsset(asset_type="CURRENCY", symbol=quote_currency, name="Tether USD", source_asset_key=quote_currency)
                session.add(currency_asset)
            
            composite_ticker = coin_symbol + quote_currency
            asset_quote = session.query(AssetQuote).filter_by(ticker=composite_ticker, data_source_id=data_source.id).first()
            if not asset_quote:
                asset_quote = AssetQuote(
                    from_asset_type="CRYPTO",
                    from_asset_symbol=coin_symbol,
                    to_asset_type="CURRENCY",
                    to_asset_symbol=quote_currency,
                    data_source_id=data_source.id,
                    ticker=composite_ticker,
                    source_ticker=composite_ticker
                )
                session.add(asset_quote)
            else:
                asset_quote.source_ticker = composite_ticker

            if coin_id in historical_data and historical_data[coin_id] is not None:
                df = historical_data[coin_id]
                for date, row_data in df.iterrows():
                    price_date = date if isinstance(date, datetime.datetime) else datetime.datetime.combine(date, datetime.time())
                    exists = session.query(AssetOHLCV).filter_by(asset_quote_id=asset_quote.id, price_date=price_date).first()
                    if exists:
                        if upsert:
                            exists.open_price = safe_convert(row_data.get("open"), float)
                            exists.high_price = safe_convert(row_data.get("high"), float)
                            exists.low_price = safe_convert(row_data.get("low"), float)
                            exists.close_price = safe_convert(row_data.get("close"), float)
                            exists.volume = safe_convert(row_data.get("volume"), Decimal)
                    else:
                        ohlcv = AssetOHLCV(
                            asset_quote=asset_quote,
                            price_date=price_date,
                            open_price=safe_convert(row_data.get("open"), float),
                            high_price=safe_convert(row_data.get("high"), float),
                            low_price=safe_convert(row_data.get("low"), float),
                            close_price=safe_convert(row_data.get("close"), float),
                            volume=safe_convert(row_data.get("volume"), Decimal)
                        )
                        session.add(ohlcv)
        session.commit()
    except SQLAlchemyError as e:
        session.rollback()
        logger.error(f"Error updating crypto assets and quotes: {e}")
        raise
    finally:
        session.close()

def update_currency_asset_and_quote(currency_list, historical_data, upsert=False):
    session = Session()
    try:
        data_source = session.query(DataSource).filter_by(name="AlphaVantage").first()
        if not data_source:
            data_source = DataSource(name="AlphaVantage", description="AlphaVantage FX data source")
            session.add(data_source)
            session.commit()

        for currency_code, currency_name in currency_list:
            asset = session.query(CurrencyAsset).filter_by(asset_type="CURRENCY", symbol=currency_code).first()
            if not asset:
                asset = CurrencyAsset(asset_type="CURRENCY", symbol=currency_code, name=currency_name, source_asset_key=currency_code)
                session.add(asset)
            else:
                asset.name = currency_name
                asset.source_asset_key = currency_code
            
            composite_ticker = currency_code + "USD"
            asset_quote = session.query(AssetQuote).filter_by(ticker=composite_ticker, data_source_id=data_source.id).first()
            if not asset_quote:
                asset_quote = AssetQuote(
                    from_asset_type="CURRENCY",
                    from_asset_symbol=currency_code,
                    to_asset_type="CURRENCY",
                    to_asset_symbol="USD",
                    data_source_id=data_source.id,
                    ticker=composite_ticker,
                    source_ticker=currency_code
                )
                session.add(asset_quote)
            else:
                asset_quote.source_ticker = currency_code

            if currency_code in historical_data and historical_data[currency_code] is not None:
                df = historical_data[currency_code]
                for date, row_data in df.iterrows():
                    price_date = date if isinstance(date, datetime.datetime) else datetime.datetime.combine(date, datetime.time())
                    exists = session.query(AssetOHLCV).filter_by(asset_quote_id=asset_quote.id, price_date=price_date).first()
                    if exists:
                        if upsert:
                            exists.open_price = safe_convert(row_data.get("Open"), float)
                            exists.high_price = safe_convert(row_data.get("High"), float)
                            exists.low_price = safe_convert(row_data.get("Low"), float)
                            exists.close_price = safe_convert(row_data.get("Close"), float)
                            exists.volume = None
                    else:
                        ohlcv = AssetOHLCV(
                            asset_quote=asset_quote,
                            price_date=price_date,
                            open_price=safe_convert(row_data.get("Open"), float),
                            high_price=safe_convert(row_data.get("High"), float),
                            low_price=safe_convert(row_data.get("Low"), float),
                            close_price=safe_convert(row_data.get("Close"), float),
                            volume=None
                        )
                        session.add(ohlcv)
        session.commit()
    except SQLAlchemyError as e:
        session.rollback()
        logger.error(f"Error updating currency assets and quotes: {e}")
        raise
    finally:
        session.close()

def full_sync_stocks():
    import yfinance as yf
    from config import HISTORICAL_START_DATE, MAX_TICKERS_PER_REQUEST, REQUEST_DELAY_SECONDS
    logger.info("Starting Global Full Sync for Stocks...")
    query_th = yf.EquityQuery("eq", ["region", "th"])
    quotes_df_th, historical_data_th = fetch_yf_data(MAX_TICKERS_PER_REQUEST, REQUEST_DELAY_SECONDS, query_th, start_date=HISTORICAL_START_DATE)
    query_us = yf.EquityQuery("is-in", ["exchange", "NMS", "NYQ"])
    quotes_df_us, historical_data_us = fetch_yf_data(MAX_TICKERS_PER_REQUEST, REQUEST_DELAY_SECONDS, query_us, start_date=HISTORICAL_START_DATE)
    quotes_df = pd.concat([quotes_df_th, quotes_df_us], ignore_index=True)
    historical_data = {**historical_data_th, **historical_data_us}
    update_stock_asset_and_quote(quotes_df, historical_data, upsert=False)
    session = Session()
    try:
        state = session.query(DeltaSyncState).filter_by(id=1).first()
        if not state:
            state = DeltaSyncState(id=1)
        state.last_full_sync = datetime.datetime.now()
        session.merge(state)
        session.commit()
    except Exception as e:
        session.rollback()
        logger.error(f"Error updating delta sync state for stocks full sync: {e}")
        raise
    finally:
        session.close()
    logger.info("Global Full Sync for Stocks Completed.")

def delta_sync_stocks():
    import yfinance as yf
    from config import MAX_TICKERS_PER_REQUEST, REQUEST_DELAY_SECONDS
    logger.info("Starting Global Delta Sync for Stocks...")
    session = Session()
    state = session.query(DeltaSyncState).filter_by(id=1).first()
    session.close()
    today = datetime.datetime.now().date()
    two_days_ago = today - datetime.timedelta(days=2)
    query_th = yf.EquityQuery("eq", ["region", "th"])
    quotes_df_th, historical_data_th = fetch_yf_data(MAX_TICKERS_PER_REQUEST, REQUEST_DELAY_SECONDS, query_th,
                                                       start_date=two_days_ago.strftime("%Y-%m-%d"),
                                                       end_date=today.strftime("%Y-%m-%d"))
    query_us = yf.EquityQuery("is-in", ["exchange", "NMS", "NYQ"])
    quotes_df_us, historical_data_us = fetch_yf_data(MAX_TICKERS_PER_REQUEST, REQUEST_DELAY_SECONDS, query_us,
                                                       start_date=two_days_ago.strftime("%Y-%m-%d"),
                                                       end_date=today.strftime("%Y-%m-%d"))
    quotes_df = pd.concat([quotes_df_th, quotes_df_us], ignore_index=True)
    historical_data = {**historical_data_th, **historical_data_us}
    update_stock_asset_and_quote(quotes_df, historical_data, upsert=True)
    session = Session()
    try:
        state = session.query(DeltaSyncState).filter_by(id=1).first()
        if not state:
            state = DeltaSyncState(id=1)
        state.last_delta_sync = datetime.datetime.now()
        session.merge(state)
        session.commit()
    except Exception as e:
        session.rollback()
        logger.error(f"Error updating delta sync state for stocks delta sync: {e}")
        raise
    finally:
        session.close()
    logger.info("Global Delta Sync for Stocks Completed.")

def full_sync_crypto():
    from config import HISTORICAL_START_DATE, REQUEST_DELAY_SECONDS
    logger.info("Starting Global Full Sync for Cryptocurrencies...")
    crypto_data = fetch_coingecko_data()
    historical_data = {}
    for coin in crypto_data:
        coin_id = coin.get("id")
        symbol = coin.get("symbol").upper() + "USDT"
        df = fetch_binance_crypto_data(symbol, HISTORICAL_START_DATE, None)
        historical_data[coin_id] = df
        time.sleep(REQUEST_DELAY_SECONDS)
    update_crypto_asset_and_quote(crypto_data, historical_data, upsert=False)
    session = Session()
    try:
        state = session.query(DeltaSyncState).filter_by(id=1).first()
        if not state:
            state = DeltaSyncState(id=1)
        state.last_full_sync = datetime.datetime.now()
        session.merge(state)
        session.commit()
    except Exception as e:
        session.rollback()
        logger.error(f"Error updating delta sync state for crypto full sync: {e}")
        raise
    finally:
        session.close()
    logger.info("Global Full Sync for Cryptocurrencies Completed.")

def delta_sync_crypto():
    from config import HISTORICAL_START_DATE, REQUEST_DELAY_SECONDS
    logger.info("Starting Global Delta Sync for Cryptocurrencies...")
    session = Session()
    state = session.query(DeltaSyncState).filter_by(id=1).first()
    session.close()
    today = datetime.datetime.now().date()
    two_days_ago = today - datetime.timedelta(days=2)
    crypto_data = fetch_coingecko_data()
    historical_data = {}
    for coin in crypto_data:
        coin_id = coin.get("id")
        symbol = coin.get("symbol").upper() + "USDT"
        df = fetch_binance_crypto_data(symbol, two_days_ago.strftime("%Y-%m-%d"), today.strftime("%Y-%m-%d"))
        historical_data[coin_id] = df
        time.sleep(REQUEST_DELAY_SECONDS)
    update_crypto_asset_and_quote(crypto_data, historical_data, upsert=True)
    session = Session()
    try:
        state = session.query(DeltaSyncState).filter_by(id=1).first()
        if not state:
            state = DeltaSyncState(id=1)
        state.last_delta_sync = datetime.datetime.now()
        session.merge(state)
        session.commit()
    except Exception as e:
        session.rollback()
        logger.error(f"Error updating delta sync state for crypto delta sync: {e}")
        raise
    finally:
        session.close()
    logger.info("Global Delta Sync for Cryptocurrencies Completed.")

def full_sync_currency(ticker=None):
    from config import HISTORICAL_START_DATE, REQUEST_DELAY_SECONDS
    from utils import get_currency_list
    import pandas as pd
    if ticker:
        logger.info(f"Starting Full Sync for Currency: {ticker}...")
    else:
        logger.info("Starting Global Full Sync for Currencies...")
    currency_list = get_currency_list()
    if ticker:
        currency_list = [(code, name) for code, name in currency_list if code.upper() == ticker.upper()]
        if not currency_list:
            logger.error(f"Ticker {ticker} not found in currency list.")
            raise ValueError("Ticker not found")
    historical_data = {}
    from data_fetchers import fetch_fx_daily_data
    for currency_code, _ in currency_list:
        if currency_code.upper() == "USD":
            df = pd.DataFrame({
                "Open": [1.0],
                "High": [1.0],
                "Low": [1.0],
                "Close": [1.0]
            }, index=[pd.to_datetime(HISTORICAL_START_DATE)])
            historical_data[currency_code] = df
        else:
            df = fetch_fx_daily_data(currency_code, "USD", outputsize="full")
            if df is None or df.empty:
                logger.error(f"Failed to fetch FX daily data for {currency_code}/USD")
            historical_data[currency_code] = df
        time.sleep(REQUEST_DELAY_SECONDS)
    update_currency_asset_and_quote(currency_list, historical_data, upsert=False)
    session = Session()
    try:
        state = session.query(DeltaSyncState).filter_by(id=1).first()
        if not state:
            state = DeltaSyncState(id=1)
        state.last_full_sync = datetime.datetime.now()
        session.merge(state)
        session.commit()
    except Exception as e:
        session.rollback()
        logger.error(f"Error updating delta sync state for currency full sync: {e}")
        raise
    finally:
        session.close()
    if ticker:
        logger.info(f"Full Sync for Currency {ticker} Completed.")
    else:
        logger.info("Global Full Sync for Currencies Completed.")

def delta_sync_currency(ticker=None):
    from config import REQUEST_DELAY_SECONDS
    from utils import get_currency_list
    import pandas as pd
    if ticker:
        logger.info(f"Starting Delta Sync for Currency: {ticker}...")
    else:
        logger.info("Starting Global Delta Sync for Currencies...")
    session = Session()
    state = session.query(DeltaSyncState).filter_by(id=1).first()
    session.close()
    today = datetime.datetime.now().date()
    two_days_ago = today - datetime.timedelta(days=2)
    currency_list = get_currency_list()
    if ticker:
        currency_list = [(code, name) for code, name in currency_list if code.upper() == ticker.upper()]
        if not currency_list:
            logger.error(f"Ticker {ticker} not found in currency list.")
            raise ValueError("Ticker not found")
    historical_data = {}
    from data_fetchers import fetch_fx_daily_data
    for currency_code, _ in currency_list:
        if currency_code.upper() == "USD":
            df = pd.DataFrame({
                "Open": [1.0],
                "High": [1.0],
                "Low": [1.0],
                "Close": [1.0]
            }, index=[pd.to_datetime(two_days_ago.strftime("%Y-%m-%d"))])
            historical_data[currency_code] = df
        else:
            df = fetch_fx_daily_data(currency_code, "USD", outputsize="full")
            if df is None or df.empty:
                logger.error(f"Failed to fetch FX daily data for {currency_code}/USD")
            historical_data[currency_code] = df
        time.sleep(REQUEST_DELAY_SECONDS)
    update_currency_asset_and_quote(currency_list, historical_data, upsert=True)
    session = Session()
    try:
        state = session.query(DeltaSyncState).filter_by(id=1).first()
        if not state:
            state = DeltaSyncState(id=1)
        state.last_delta_sync = datetime.datetime.now()
        session.merge(state)
        session.commit()
    except Exception as e:
        session.rollback()
        logger.error(f"Error updating delta sync state for currency delta sync: {e}")
        raise
    finally:
        session.close()
    if ticker:
        logger.info(f"Delta Sync for Currency {ticker} Completed.")
    else:
        logger.info("Global Delta Sync for Currencies Completed.")

def refresh_stock_top_n_tickers(query_counter, top_n, delay_t):
    session = Session()
    try:
        top_keys = [t[1] for t, count in query_counter.most_common(top_n) if t[0] == "STOCK"]
        asset_quotes = session.query(AssetQuote).filter(AssetQuote.ticker.in_(top_keys)).all()
    finally:
        session.close()
    from data_fetchers import StockDataSource
    source_tickers = [aq.source_ticker for aq in asset_quotes]
    prices = StockDataSource.refresh_latest_prices(source_tickers)
    now = datetime.datetime.now()
    ds_name = "YFINANCE"
    for st in source_tickers:
        if st in prices:
            expires = now + datetime.timedelta(minutes=REGULAR_TTL)
            latest_cache[(ds_name, st)] = (prices[st], now, expires)
    time.sleep(delay_t)

def refresh_crypto_prices():
    from data_fetchers import CryptoDataSource
    prices = CryptoDataSource.get_all_latest_prices()
    now = datetime.datetime.now()
    ds_name = "BINANCE"
    for ticker, price in prices.items():
        expires = now + datetime.timedelta(minutes=REGULAR_TTL)
        latest_cache[(ds_name, ticker)] = (price, now, expires)

def refresh_currency_prices():
    from data_fetchers import CurrencyDataSource
    from utils import get_currency_list
    currency_list = get_currency_list()
    codes = [code for code, name in currency_list]
    prices = CurrencyDataSource.refresh_latest_prices(codes)
    now = datetime.datetime.now()
    ds_name = "ALPHAVANTAGE"
    for code in codes:
        if code in prices:
            expires = now + datetime.timedelta(minutes=REGULAR_TTL)
            latest_cache[(ds_name, code)] = (prices[code], now, expires)

def refresh_all_latest_prices():
    from config import REQUEST_DELAY_SECONDS, TOP_N_TICKERS
    from utils import query_counter
    refresh_stock_top_n_tickers(query_counter, TOP_N_TICKERS, REQUEST_DELAY_SECONDS)
    refresh_crypto_prices()
    # refresh_currency_prices()
    import cache_storage
    cache_storage.last_cache_refresh = datetime.datetime.now()
