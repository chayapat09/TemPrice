import datetime
import time
import traceback
import pandas as pd
from decimal import Decimal, InvalidOperation  # Import InvalidOperation
from models import Asset, StockAsset, CryptoAsset, CurrencyAsset, DataSource, AssetQuote, AssetOHLCV, DeltaSyncState, Session
# Added fetch_fx_daily_data, CurrencyDataSource etc
from data_fetchers import fetch_yf_data_for_ticker, fetch_yf_data, fetch_coingecko_data, fetch_binance_crypto_data, fetch_fx_daily_data, CurrencyDataSource, StockDataSource, CryptoDataSource
from utils import safe_convert, get_currency_list  # Added get_currency_list
from sqlalchemy.exc import SQLAlchemyError
import logging
# Import necessary configs
from config import REGULAR_TTL, HISTORICAL_START_DATE, REQUEST_DELAY_SECONDS, MAX_TICKERS_PER_REQUEST, TOP_N_TICKERS
from cache_storage import latest_cache, last_cache_refresh  # Corrected import
import yfinance as yf

logger = logging.getLogger(__name__)

# --- Helper function for safe decimal conversion ---


def safe_decimal(value, precision='0.00000001'):
    """Safely converts a value to Decimal, handling None and potential errors."""
    if value is None or pd.isna(value):
        return None
    try:
        # Ensure the value is a string before converting to Decimal if it's float
        # to avoid potential floating point inaccuracies
        if isinstance(value, float):
            value_str = f"{value:.10f}"  # Adjust precision as needed
        else:
            value_str = str(value)
        return Decimal(value_str).quantize(Decimal(precision))
    except (TypeError, ValueError, InvalidOperation):
        return None


# --- Update Functions (with improved safe_convert usage) ---

def update_stock_asset_and_quote(quotes_df, historical_data, upsert=False):
    session = Session()
    try:
        # Preload or create yFinance data source
        data_source = session.query(
            DataSource).filter_by(name="yFinance").first()
        if not data_source:
            data_source = DataSource(
                name="yFinance", description="Yahoo Finance data source")
            session.add(data_source)
            session.flush()  # Get ID for relationships
            logger.info("Created DataSource: yFinance")

        # Preload USD currency asset (common case)
        usd_asset = session.query(
            CurrencyAsset).filter_by(symbol="USD").first()
        if not usd_asset:
            usd_asset = CurrencyAsset(
                asset_type="CURRENCY", symbol="USD", name="US Dollar", source_asset_key="USD")
            session.add(usd_asset)
            logger.info("Created CurrencyAsset: USD")
            session.flush()  # Ensure it's available

        # Process tickers from quotes_df
        tickers_to_process = quotes_df["symbol"].dropna().unique().tolist()
        if not tickers_to_process:
            logger.warning(
                "No valid stock tickers found in quotes_df to process.")
            return

        logger.info(f"Processing {len(tickers_to_process)} stock tickers...")

        # Preload existing stock assets and asset quotes
        existing_assets = {asset.symbol: asset for asset in session.query(
            StockAsset).filter(StockAsset.symbol.in_(tickers_to_process)).all()}
        logger.info(
            f"Found {len(existing_assets)} existing stock assets in DB.")

        # Determine quote currencies (simplified logic, default USD)
        # A more robust solution would fetch currency info per ticker/exchange
        ticker_currency_map = {}
        required_currencies = set(["USD"])  # Always need USD
        for idx, row in quotes_df.iterrows():
            ticker = row.get("symbol")
            if not ticker:
                continue
            # Example: Use exchange info if available, otherwise default
            currency = row.get("currency")
            if not currency:
                # Fallback case: if exchange equals "SET", use "THB"; otherwise default to "USD".
                exchange = row.get("exchange")
                if exchange == "SET":
                    currency = "THB"
                else:
                    currency = "USD"
            # Add more mappings if needed
            ticker_currency_map[ticker] = currency
            required_currencies.add(currency)

        # Preload required currency assets
        existing_currency_assets = {asset.symbol: asset for asset in session.query(
            CurrencyAsset).filter(CurrencyAsset.symbol.in_(list(required_currencies))).all()}
        logger.info(
            f"Found {len(existing_currency_assets)} existing currency assets for quoting.")

        # Preload existing asset quotes
        composite_tickers = [
            t + ticker_currency_map.get(t, 'USD') for t in tickers_to_process]
        existing_asset_quotes = {aq.ticker: aq for aq in session.query(AssetQuote).filter(
            AssetQuote.ticker.in_(composite_tickers), AssetQuote.data_source_id == data_source.id).all()}
        logger.info(
            f"Found {len(existing_asset_quotes)} existing relevant asset quotes.")

        # --- Iterate and Update/Insert ---
        total_new_ohlcv = 0
        total_updated_ohlcv = 0

        for idx, row in quotes_df.iterrows():
            ticker = row.get("symbol")
            if not ticker:
                continue

            # --- Asset Update/Insert ---
            asset = existing_assets.get(ticker)
            name = row.get("longName") or row.get("displayName") or ticker
            first_trade_raw = row.get(
                "firstTradeDateEpochUtc")  # YF uses this now
            first_trade = None
            if first_trade_raw:
                try:
                    # Convert from seconds timestamp
                    first_trade = datetime.datetime.utcfromtimestamp(
                        first_trade_raw).date()
                except Exception:
                    logger.warning(
                        f"Could not parse first_trade_date for {ticker}: {first_trade_raw}")

            if not asset:
                asset = StockAsset(
                    asset_type="STOCK",
                    symbol=ticker,
                    name=name,
                    language=row.get("language"),
                    region=row.get("region"),
                    exchange=row.get("exchange"),
                    full_exchange_name=row.get("fullExchangeName"),
                    first_trade_date=first_trade,
                    source_asset_key=ticker  # yFinance uses the ticker symbol
                )
                session.add(asset)
                # Add to map for quote creation
                existing_assets[ticker] = asset
                logger.debug(f"Adding new StockAsset: {ticker}")
            else:
                # Update existing asset fields if necessary
                asset.name = name
                asset.language = row.get("language")
                asset.region = row.get("region")
                asset.exchange = row.get("exchange")
                asset.full_exchange_name = row.get("fullExchangeName")
                asset.first_trade_date = first_trade
                asset.source_asset_key = ticker
                logger.debug(f"Updating existing StockAsset: {ticker}")

            # --- Quote Currency Asset ---
            quote_currency_code = ticker_currency_map.get(ticker, 'USD')
            currency_asset = existing_currency_assets.get(quote_currency_code)
            if not currency_asset:
                # Create missing currency asset (should be rare if prepopulated)
                currency_asset = CurrencyAsset(asset_type="CURRENCY", symbol=quote_currency_code,
                                               name=f"{quote_currency_code} (Auto-created)", source_asset_key=quote_currency_code)
                session.add(currency_asset)
                existing_currency_assets[quote_currency_code] = currency_asset
                logger.warning(
                    f"Auto-created missing CurrencyAsset: {quote_currency_code}")
                session.flush()  # Get ID

            # --- AssetQuote Update/Insert ---
            composite_ticker = ticker + quote_currency_code
            asset_quote = existing_asset_quotes.get(composite_ticker)

            if not asset_quote:
                asset_quote = AssetQuote(
                    from_asset_type="STOCK",
                    from_asset_symbol=ticker,
                    to_asset_type="CURRENCY",
                    to_asset_symbol=quote_currency_code,
                    data_source_id=data_source.id,
                    ticker=composite_ticker,
                    source_ticker=ticker  # Source ticker for yFinance is the stock symbol
                )
                session.add(asset_quote)
                session.flush()  # Get the ID for OHLCV
                existing_asset_quotes[composite_ticker] = asset_quote
                logger.debug(f"Adding new AssetQuote: {composite_ticker}")
            else:
                # Ensure source_ticker is correct (usually won't change for yFinance)
                asset_quote.source_ticker = ticker
                logger.debug(f"Using existing AssetQuote: {composite_ticker}")

            # --- OHLCV Update/Insert ---
            if ticker in historical_data and historical_data[ticker] is not None and not historical_data[ticker].empty:
                df = historical_data[ticker]

                # Preload existing OHLCV for this *specific* quote ID for efficiency within loop if needed often
                # Or rely on bulk operations which handle existence checks
                # Let's proceed with bulk approach

                new_records_maps = []
                update_mappings = []

                # Fetch existing records for the date range being processed
                min_date = df.index.min().to_pydatetime().replace(
                    hour=0, minute=0, second=0, microsecond=0)
                max_date = df.index.max().to_pydatetime().replace(
                    hour=0, minute=0, second=0, microsecond=0)

                existing_ohlcv_for_quote = {
                    rec.price_date: rec
                    for rec in session.query(AssetOHLCV).filter(
                        AssetOHLCV.asset_quote_id == asset_quote.id,
                        AssetOHLCV.price_date >= min_date,
                        AssetOHLCV.price_date <= max_date
                    ).all()
                }
                logger.debug(
                    f"Found {len(existing_ohlcv_for_quote)} existing OHLCV records for {composite_ticker} in date range.")

                for date_idx, row_data in df.iterrows():
                    # Ensure date is datetime object at midnight UTC? Or keep original timezone?
                    # yfinance usually returns tz-aware or naive based on market. Let's make it naive midnight UTC.
                    price_date = date_idx.to_pydatetime()
                    if price_date.tzinfo:
                        from datetime import timezone
                        price_date = price_date.astimezone(
                            timezone.utc).replace(tzinfo=None)
                    price_date = price_date.replace(
                        hour=0, minute=0, second=0, microsecond=0)

                    ohlcv_data = {
                        "open_price": safe_decimal(row_data.get("Open")),
                        "high_price": safe_decimal(row_data.get("High")),
                        "low_price": safe_decimal(row_data.get("Low")),
                        "close_price": safe_decimal(row_data.get("Close")),
                        # Volume precision can be lower
                        "volume": safe_decimal(row_data.get("Volume"), precision='0.01')
                    }

                    existing_record = existing_ohlcv_for_quote.get(price_date)

                    if existing_record:
                        if upsert:
                            # Check if data actually changed to avoid unnecessary updates
                            changed = False
                            for key, value in ohlcv_data.items():
                                if getattr(existing_record, key) != value:
                                    changed = True
                                    break
                            if changed:
                                update_map = {"id": existing_record.id}
                                update_map.update(ohlcv_data)
                                update_mappings.append(update_map)
                        # else: Skip if not upserting and record exists
                    else:
                        # New record
                        new_map = {"asset_quote_id": asset_quote.id,
                                   "price_date": price_date}
                        new_map.update(ohlcv_data)
                        new_records_maps.append(new_map)

                if new_records_maps:
                    try:
                        session.bulk_insert_mappings(
                            AssetOHLCV, new_records_maps)
                        logger.debug(
                            f"Bulk inserted {len(new_records_maps)} OHLCV for {composite_ticker}.")
                        total_new_ohlcv += len(new_records_maps)
                    except SQLAlchemyError as bulk_e:
                        logger.error(
                            f"Error bulk inserting OHLCV for {composite_ticker}: {bulk_e}")
                        session.rollback()  # Rollback partial bulk insert
                        # Optionally try individual inserts here
                        raise
                if update_mappings:
                    try:
                        session.bulk_update_mappings(
                            AssetOHLCV, update_mappings)
                        logger.debug(
                            f"Bulk updated {len(update_mappings)} OHLCV for {composite_ticker}.")
                        total_updated_ohlcv += len(update_mappings)
                    except SQLAlchemyError as bulk_e:
                        logger.error(
                            f"Error bulk updating OHLCV for {composite_ticker}: {bulk_e}")
                        session.rollback()  # Rollback partial bulk update
                        raise
            else:
                logger.warning(
                    f"No historical data found or provided for stock ticker: {ticker}")

        session.commit()
        logger.info(
            f"Stock asset/quote/OHLCV update finished. New OHLCV: {total_new_ohlcv}, Updated OHLCV: {total_updated_ohlcv}.")

    except SQLAlchemyError as e:
        session.rollback()
        logger.error(
            f"Database error during stock update: {e}\n{traceback.format_exc()}")
        raise
    except Exception as e:
        session.rollback()
        logger.error(
            f"Unexpected error during stock update: {e}\n{traceback.format_exc()}")
        raise
    finally:
        session.close()


def update_crypto_asset_and_quote(crypto_data, historical_data, upsert=False):
    session = Session()
    try:
        # Preload or create Binance data source
        data_source = session.query(
            DataSource).filter_by(name="Binance").first()
        if not data_source:
            data_source = DataSource(
                name="Binance", description="Binance API data source (for OHLCV)")
            session.add(data_source)
            session.flush()
            logger.info("Created DataSource: Binance")

        # Preload USDT currency asset
        usdt_asset = session.query(Asset).filter(
            Asset.asset_type == "CURRENCY", Asset.symbol == "USDT").first()  # Use Asset base class
        if not usdt_asset:
            # USDT itself is technically often a crypto asset, but we treat it as the quote CURRENCY here
            usdt_asset = CurrencyAsset(
                asset_type="CURRENCY", symbol="USDT", name="Tether USD", source_asset_key="USDT")
            session.add(usdt_asset)
            logger.info("Created Asset: USDT (as CURRENCY)")
            session.flush()

        # Process coins from crypto_data (metadata from CoinGecko)
        coin_ids_to_process = [c.get("id") for c in crypto_data if c.get("id")]
        if not coin_ids_to_process:
            logger.warning(
                "No valid crypto IDs found in crypto_data to process.")
            return

        logger.info(f"Processing {len(coin_ids_to_process)} crypto assets...")

        coin_id_map = {c['id']: c for c in crypto_data if c.get('id')}
        coin_symbols = [c.get("symbol", "").upper()
                        for c in crypto_data if c.get("symbol")]

        # Preload existing crypto assets and asset quotes
        existing_assets = {asset.symbol: asset for asset in session.query(
            CryptoAsset).filter(CryptoAsset.symbol.in_(coin_symbols)).all()}
        logger.info(
            f"Found {len(existing_assets)} existing crypto assets in DB.")

        composite_tickers = [symbol + "USDT" for symbol in coin_symbols]
        existing_asset_quotes = {aq.ticker: aq for aq in session.query(AssetQuote).filter(
            AssetQuote.ticker.in_(composite_tickers), AssetQuote.data_source_id == data_source.id).all()}
        logger.info(
            f"Found {len(existing_asset_quotes)} existing relevant crypto asset quotes.")

        # --- Iterate and Update/Insert ---
        total_new_ohlcv = 0
        total_updated_ohlcv = 0

        for coin_id in coin_ids_to_process:
            coin = coin_id_map.get(coin_id)
            if not coin:
                continue  # Should not happen

            coin_symbol = coin.get("symbol", "").upper()
            if not coin_symbol:
                continue

            # --- Asset Update/Insert ---
            asset = existing_assets.get(coin_symbol)
            name = coin.get("name") or coin_symbol

            # Safe conversions for potentially None values from CoinGecko
            ath_date = pd.to_datetime(coin.get("ath_date"), errors='coerce').to_pydatetime(
            ) if coin.get("ath_date") else None
            atl_date = pd.to_datetime(coin.get("atl_date"), errors='coerce').to_pydatetime(
            ) if coin.get("atl_date") else None

            if not asset:
                asset = CryptoAsset(
                    asset_type="CRYPTO",
                    symbol=coin_symbol,
                    name=name,
                    source_asset_key=coin_id,  # Store CoinGecko ID as source key
                    image=coin.get("image"),
                    ath=safe_decimal(coin.get("ath")),
                    ath_date=ath_date,
                    atl=safe_decimal(coin.get("atl")),
                    atl_date=atl_date,
                    total_supply=safe_convert(coin.get("total_supply"), int),
                    max_supply=safe_convert(coin.get("max_supply"), int)
                )
                session.add(asset)
                existing_assets[coin_symbol] = asset
                logger.debug(f"Adding new CryptoAsset: {coin_symbol}")
            else:
                asset.name = name
                asset.source_asset_key = coin_id
                asset.image = coin.get("image")
                asset.ath = safe_decimal(coin.get("ath"))
                asset.ath_date = ath_date
                asset.atl = safe_decimal(coin.get("atl"))
                asset.atl_date = atl_date
                asset.total_supply = safe_convert(
                    coin.get("total_supply"), int)
                asset.max_supply = safe_convert(coin.get("max_supply"), int)
                logger.debug(f"Updating existing CryptoAsset: {coin_symbol}")

            # --- AssetQuote Update/Insert ---
            composite_ticker = coin_symbol + "USDT"
            # Source ticker for Binance is the composite symbol itself (e.g., BTCUSDT)
            binance_source_ticker = composite_ticker
            asset_quote = existing_asset_quotes.get(composite_ticker)

            if not asset_quote:
                asset_quote = AssetQuote(
                    from_asset_type="CRYPTO",
                    from_asset_symbol=coin_symbol,
                    to_asset_type="CURRENCY",  # Quoting against USDT
                    to_asset_symbol="USDT",
                    data_source_id=data_source.id,  # Binance for OHLCV
                    ticker=composite_ticker,
                    source_ticker=binance_source_ticker
                )
                session.add(asset_quote)
                session.flush()  # Get ID
                existing_asset_quotes[composite_ticker] = asset_quote
                logger.debug(f"Adding new AssetQuote: {composite_ticker}")
            else:
                asset_quote.source_ticker = binance_source_ticker
                logger.debug(f"Using existing AssetQuote: {composite_ticker}")

            # --- OHLCV Update/Insert ---
            if coin_id in historical_data and historical_data[coin_id] is not None and not historical_data[coin_id].empty:
                df = historical_data[coin_id]
                new_records_maps = []
                update_mappings = []

                # Fetch existing records for the date range
                min_date = df.index.min().to_pydatetime().replace(
                    hour=0, minute=0, second=0, microsecond=0)
                max_date = df.index.max().to_pydatetime().replace(
                    hour=0, minute=0, second=0, microsecond=0)

                existing_ohlcv_for_quote = {
                    rec.price_date: rec
                    for rec in session.query(AssetOHLCV).filter(
                        AssetOHLCV.asset_quote_id == asset_quote.id,
                        AssetOHLCV.price_date >= min_date,
                        AssetOHLCV.price_date <= max_date
                    ).all()
                }
                logger.debug(
                    f"Found {len(existing_ohlcv_for_quote)} existing OHLCV records for {composite_ticker} in date range.")

                for date_idx, row_data in df.iterrows():
                    # Binance data is typically UTC midnight timestamps
                    price_date = date_idx.to_pydatetime()
                    if price_date.tzinfo:
                        from datetime import timezone
                        price_date = price_date.astimezone(
                            timezone.utc).replace(tzinfo=None)
                    price_date = price_date.replace(
                        hour=0, minute=0, second=0, microsecond=0)

                    ohlcv_data = {
                        "open_price": safe_decimal(row_data.get("open")),
                        "high_price": safe_decimal(row_data.get("high")),
                        "low_price": safe_decimal(row_data.get("low")),
                        "close_price": safe_decimal(row_data.get("close")),
                        "volume": safe_decimal(row_data.get("volume"), precision='0.01')
                    }

                    existing_record = existing_ohlcv_for_quote.get(
                        price_date)

                    if existing_record:
                        if upsert:
                            changed = False
                            for key, value in ohlcv_data.items():
                                if getattr(existing_record, key) != value:
                                    changed = True
                                    break
                            if changed:
                                update_map = {"id": existing_record.id}
                                update_map.update(ohlcv_data)
                                update_mappings.append(update_map)
                    else:
                        new_map = {"asset_quote_id": asset_quote.id,
                                   "price_date": price_date}
                        new_map.update(ohlcv_data)
                        new_records_maps.append(new_map)

                if new_records_maps:
                    try:
                        session.bulk_insert_mappings(
                            AssetOHLCV, new_records_maps)
                        logger.debug(
                            f"Bulk inserted {len(new_records_maps)} OHLCV for {composite_ticker}.")
                        total_new_ohlcv += len(new_records_maps)
                    except SQLAlchemyError as bulk_e:
                        logger.error(
                            f"Error bulk inserting OHLCV for {composite_ticker}: {bulk_e}")
                        session.rollback()
                        raise
                if update_mappings:
                    try:
                        session.bulk_update_mappings(
                            AssetOHLCV, update_mappings)
                        logger.debug(
                            f"Bulk updated {len(update_mappings)} OHLCV for {composite_ticker}.")
                        total_updated_ohlcv += len(update_mappings)
                    except SQLAlchemyError as bulk_e:
                        logger.error(
                            f"Error bulk updating OHLCV for {composite_ticker}: {bulk_e}")
                        session.rollback()
                        raise
            else:
                logger.warning(
                    f"No historical data found or provided for crypto ID: {coin_id} (Symbol: {coin_symbol})")

        session.commit()
        logger.info(
            f"Crypto asset/quote/OHLCV update finished. New OHLCV: {total_new_ohlcv}, Updated OHLCV: {total_updated_ohlcv}.")

    except SQLAlchemyError as e:
        session.rollback()
        logger.error(
            f"Database error during crypto update: {e}\n{traceback.format_exc()}")
        raise
    except Exception as e:
        session.rollback()
        logger.error(
            f"Unexpected error during crypto update: {e}\n{traceback.format_exc()}")
        raise
    finally:
        session.close()


def update_currency_asset_and_quote(currency_list, historical_data, upsert=False):
    session = Session()
    try:
        # Preload or create AlphaVantage data source
        data_source = session.query(DataSource).filter_by(
            name="AlphaVantage").first()
        if not data_source:
            data_source = DataSource(
                name="AlphaVantage", description="AlphaVantage FX data source")
            session.add(data_source)
            session.flush()
            logger.info("Created DataSource: AlphaVantage")

        # Preload USD currency asset (common quote target)
        usd_asset = session.query(
            CurrencyAsset).filter_by(symbol="USD").first()
        if not usd_asset:
            usd_asset = CurrencyAsset(
                asset_type="CURRENCY", symbol="USD", name="US Dollar", source_asset_key="USD")
            session.add(usd_asset)
            logger.info("Created CurrencyAsset: USD")
            session.flush()

        currency_codes = [code for code, name in currency_list]
        if not currency_codes:
            logger.warning("No currency codes provided to update.")
            return

        logger.info(f"Processing {len(currency_codes)} currency assets...")

        # Preload existing currency assets and asset quotes (assuming quote against USD)
        existing_assets = {asset.symbol: asset for asset in session.query(
            CurrencyAsset).filter(CurrencyAsset.symbol.in_(currency_codes)).all()}
        logger.info(
            f"Found {len(existing_assets)} existing currency assets in DB.")

        # Don't create USDUSD
        composite_tickers = [
            code + "USD" for code in currency_codes if code != "USD"]
        existing_asset_quotes = {aq.ticker: aq for aq in session.query(AssetQuote).filter(
            AssetQuote.ticker.in_(composite_tickers), AssetQuote.data_source_id == data_source.id).all()}
        logger.info(
            f"Found {len(existing_asset_quotes)} existing relevant currency asset quotes.")

        # --- Iterate and Update/Insert ---
        total_new_ohlcv = 0
        total_updated_ohlcv = 0

        for currency_code, currency_name in currency_list:
            if not currency_code or not currency_name:
                continue

            # --- Asset Update/Insert ---
            asset = existing_assets.get(currency_code)
            if not asset:
                asset = CurrencyAsset(
                    asset_type="CURRENCY",
                    symbol=currency_code,
                    name=currency_name,
                    source_asset_key=currency_code  # AlphaVantage uses the code
                )
                session.add(asset)
                existing_assets[currency_code] = asset
                logger.debug(f"Adding new CurrencyAsset: {currency_code}")
            else:
                asset.name = currency_name
                asset.source_asset_key = currency_code
                logger.debug(
                    f"Updating existing CurrencyAsset: {currency_code}")

            # --- AssetQuote Update/Insert (Skip for USD itself) ---
            if currency_code == "USD":
                logger.debug(
                    "Skipping AssetQuote creation for USD against USD.")
                continue

            composite_ticker = currency_code + "USD"
            # Source ticker for AlphaVantage FX is the base currency code
            av_source_ticker = currency_code
            asset_quote = existing_asset_quotes.get(composite_ticker)

            if not asset_quote:
                asset_quote = AssetQuote(
                    from_asset_type="CURRENCY",
                    from_asset_symbol=currency_code,
                    to_asset_type="CURRENCY",
                    to_asset_symbol="USD",
                    data_source_id=data_source.id,
                    ticker=composite_ticker,
                    source_ticker=av_source_ticker
                )
                session.add(asset_quote)
                session.flush()  # Get ID
                existing_asset_quotes[composite_ticker] = asset_quote
                logger.debug(f"Adding new AssetQuote: {composite_ticker}")
            else:
                asset_quote.source_ticker = av_source_ticker
                logger.debug(f"Using existing AssetQuote: {composite_ticker}")

            # --- OHLCV Update/Insert ---
            if currency_code in historical_data and historical_data[currency_code] is not None and not historical_data[currency_code].empty:
                df = historical_data[currency_code]
                new_records_maps = []
                update_mappings = []

                # Fetch existing records for the date range
                min_date = df.index.min().to_pydatetime().replace(
                    hour=0, minute=0, second=0, microsecond=0)
                max_date = df.index.max().to_pydatetime().replace(
                    hour=0, minute=0, second=0, microsecond=0)

                existing_ohlcv_for_quote = {
                    rec.price_date: rec
                    for rec in session.query(AssetOHLCV).filter(
                        AssetOHLCV.asset_quote_id == asset_quote.id,
                        AssetOHLCV.price_date >= min_date,
                        AssetOHLCV.price_date <= max_date
                    ).all()
                }
                logger.debug(
                    f"Found {len(existing_ohlcv_for_quote)} existing OHLCV records for {composite_ticker} in date range.")

                for date_idx, row_data in df.iterrows():
                    # AlphaVantage dates are usually naive daily
                    price_date = date_idx.to_pydatetime().replace(
                        hour=0, minute=0, second=0, microsecond=0)

                    # AlphaVantage columns: '1. open', '2. high', '3. low', '4. close'
                    # Or already renamed to Open, High, Low, Close in fetcher
                    ohlcv_data = {
                        "open_price": safe_decimal(row_data.get("Open")),
                        "high_price": safe_decimal(row_data.get("High")),
                        "low_price": safe_decimal(row_data.get("Low")),
                        "close_price": safe_decimal(row_data.get("Close")),
                        "volume": None  # FX data typically doesn't have reliable volume
                    }

                    existing_record = existing_ohlcv_for_quote.get(price_date)

                    if existing_record:
                        if upsert:
                            changed = False
                            for key, value in ohlcv_data.items():
                                if getattr(existing_record, key) != value:
                                    changed = True
                                    break
                            if changed:
                                update_map = {"id": existing_record.id}
                                update_map.update(ohlcv_data)
                                update_mappings.append(update_map)
                    else:
                        new_map = {"asset_quote_id": asset_quote.id,
                                   "price_date": price_date}
                        new_map.update(ohlcv_data)
                        new_records_maps.append(new_map)

                if new_records_maps:
                    try:
                        session.bulk_insert_mappings(
                            AssetOHLCV, new_records_maps)
                        logger.debug(
                            f"Bulk inserted {len(new_records_maps)} OHLCV for {composite_ticker}.")
                        total_new_ohlcv += len(new_records_maps)
                    except SQLAlchemyError as bulk_e:
                        logger.error(
                            f"Error bulk inserting OHLCV for {composite_ticker}: {bulk_e}")
                        session.rollback()
                        raise
                if update_mappings:
                    try:
                        session.bulk_update_mappings(
                            AssetOHLCV, update_mappings)
                        logger.debug(
                            f"Bulk updated {len(update_mappings)} OHLCV for {composite_ticker}.")
                        total_updated_ohlcv += len(update_mappings)
                    except SQLAlchemyError as bulk_e:
                        logger.error(
                            f"Error bulk updating OHLCV for {composite_ticker}: {bulk_e}")
                        session.rollback()
                        raise
            else:
                logger.warning(
                    f"No historical data found or provided for currency: {currency_code}")

        session.commit()
        logger.info(
            f"Currency asset/quote/OHLCV update finished. New OHLCV: {total_new_ohlcv}, Updated OHLCV: {total_updated_ohlcv}.")

    except SQLAlchemyError as e:
        session.rollback()
        logger.error(
            f"Database error during currency update: {e}\n{traceback.format_exc()}")
        raise
    except Exception as e:
        session.rollback()
        logger.error(
            f"Unexpected error during currency update: {e}\n{traceback.format_exc()}")
        raise
    finally:
        session.close()


# --- Full Sync Functions ---

def _sync_common_update_state(sync_type="full"):
    """Helper to update DeltaSyncState after a sync operation."""
    session = Session()
    try:
        state = session.query(DeltaSyncState).filter_by(id=1).first()
        if not state:
            state = DeltaSyncState(id=1)
            session.add(state)  # Add if not exists

        now = datetime.datetime.now()
        if sync_type == "full":
            state.last_full_sync = now
        elif sync_type == "delta":
            state.last_delta_sync = now

        # Use merge for simplicity if state might be detached or already exists
        session.merge(state)
        session.commit()
        logger.info(f"Updated DeltaSyncState: last_{sync_type}_sync = {now}")
    except Exception as e:
        session.rollback()
        logger.error(
            f"Error updating delta sync state after {sync_type} sync: {e}")
        # Don't raise here, allow sync function to complete
    finally:
        session.close()


def full_sync_stocks():
    import yfinance as yf  # Keep import local if only used here
    logger.info("Starting Global Full Sync for Stocks...")
    try:
        # Consider fetching fewer tickers initially or based on popularity if full sync is too slow
        query_th = yf.EquityQuery("eq", ["region", "th"])
        quotes_df_th, historical_data_th = fetch_yf_data(
            MAX_TICKERS_PER_REQUEST, REQUEST_DELAY_SECONDS, query_th, start_date=HISTORICAL_START_DATE)
        logger.info(
            f"Fetched data for Thai stocks: {len(quotes_df_th)} quotes.")

        query_us = yf.EquityQuery("is-in", ["exchange", "NMS", "NYQ"])
        quotes_df_us, historical_data_us = fetch_yf_data(
            MAX_TICKERS_PER_REQUEST, REQUEST_DELAY_SECONDS, query_us, start_date=HISTORICAL_START_DATE)
        logger.info(f"Fetched data for US stocks: {len(quotes_df_us)} quotes.")

        if quotes_df_th.empty and quotes_df_us.empty:
            logger.warning("No stock data fetched during full sync.")
            return

        quotes_df = pd.concat([quotes_df_th, quotes_df_us], ignore_index=True)
        historical_data = {**historical_data_th, **historical_data_us}

        # Use upsert=True for simplicity
        update_stock_asset_and_quote(quotes_df, historical_data, upsert=True)
        _sync_common_update_state(sync_type="full")
        logger.info("Global Full Sync for Stocks Completed.")
    except Exception as e:
        logger.error(
            f"Global Full Sync for Stocks Failed: {e}\n{traceback.format_exc()}")


def delta_sync_stocks():
    logger.info("Starting Global Delta Sync for Stocks...")
    try:
        today = datetime.datetime.now().date()
        start_date_dt = today - datetime.timedelta(days=3)  # Fetch last 3 days
        start_date_str = start_date_dt.strftime("%Y-%m-%d")
        end_date_str = (today + datetime.timedelta(days=1)
                        ).strftime("%Y-%m-%d")  # Include today

        # Fetch tickers that are already in the DB to delta sync them
        session = Session()
        try:
            stock_tickers_th = [a.symbol for a in session.query(
                StockAsset.symbol).filter(StockAsset.region == 'th').all()]
            stock_tickers_us = [a.symbol for a in session.query(
                StockAsset.symbol).filter(StockAsset.exchange.in_(['NMS', 'NYQ'])).all()]
        finally:
            session.close()

        logger.info(
            f"Found {len(stock_tickers_th)} Thai and {len(stock_tickers_us)} US tickers in DB for delta sync.")

        all_quotes_list = []
        historical_data_combined = {}

        # Fetch TH data
        if stock_tickers_th:
            quotes_df_th, hist_th = fetch_yf_data(MAX_TICKERS_PER_REQUEST, REQUEST_DELAY_SECONDS, None,  # Don't need query, provide symbols
                                                  start_date=start_date_str, end_date=end_date_str,
                                                  ticker_list=stock_tickers_th)  # Pass explicit list
            if not quotes_df_th.empty:
                all_quotes_list.append(quotes_df_th)
            historical_data_combined.update(hist_th)
            logger.info(
                f"Delta sync - Fetched TH: {len(quotes_df_th)} quotes, {len(hist_th)} historical.")

        # Fetch US data
        if stock_tickers_us:
            quotes_df_us, hist_us = fetch_yf_data(MAX_TICKERS_PER_REQUEST, REQUEST_DELAY_SECONDS, None,
                                                  start_date=start_date_str, end_date=end_date_str,
                                                  ticker_list=stock_tickers_us)
            if not quotes_df_us.empty:
                all_quotes_list.append(quotes_df_us)
            historical_data_combined.update(hist_us)
            logger.info(
                f"Delta sync - Fetched US: {len(quotes_df_us)} quotes, {len(hist_us)} historical.")

        if not all_quotes_list:
            logger.warning("No stock data fetched during delta sync.")
            # Still update sync time? Maybe not if nothing was fetched.
            # _sync_common_update_state(sync_type="delta")
            return

        quotes_df_combined = pd.concat(all_quotes_list, ignore_index=True)

        update_stock_asset_and_quote(
            quotes_df_combined, historical_data_combined, upsert=True)
        _sync_common_update_state(sync_type="delta")
        logger.info("Global Delta Sync for Stocks Completed.")
    except Exception as e:
        logger.error(
            f"Global Delta Sync for Stocks Failed: {e}\n{traceback.format_exc()}")


def full_sync_crypto():
    logger.info("Starting Global Full Sync for Cryptocurrencies...")
    try:
        crypto_data = fetch_coingecko_data()  # Get metadata
        if not crypto_data:
            logger.warning(
                "No crypto metadata fetched from CoinGecko. Aborting full sync.")
            return

        historical_data = {}
        processed_count = 0
        for coin in crypto_data:
            coin_id = coin.get("id")
            symbol = coin.get("symbol", "").upper()
            if not coin_id or not symbol:
                continue

            binance_symbol = symbol + "USDT"
            logger.debug(
                f"Fetching full history for crypto: {binance_symbol} (ID: {coin_id})")

            df = fetch_binance_crypto_data(
                binance_symbol, HISTORICAL_START_DATE, None)
            if df is not None:  # Store even if empty, but not on error (None)
                historical_data[coin_id] = df
                logger.debug(f"Fetched {len(df)} records for {binance_symbol}")
            else:
                logger.error(
                    f"Failed to fetch historical data for {binance_symbol}")

            processed_count += 1
            # Optional: Limit the number of cryptos to sync fully if it takes too long
            # if processed_count >= 100: break
            time.sleep(REQUEST_DELAY_SECONDS)  # Rate limiting

        update_crypto_asset_and_quote(
            crypto_data, historical_data, upsert=True)  # Use upsert=True
        _sync_common_update_state(sync_type="full")
        logger.info("Global Full Sync for Cryptocurrencies Completed.")
    except Exception as e:
        logger.error(
            f"Global Full Sync for Cryptos Failed: {e}\n{traceback.format_exc()}")


def delta_sync_crypto():
    logger.info("Starting Global Delta Sync for Cryptocurrencies...")
    try:
        today = datetime.datetime.now().date()
        start_date_dt = today - datetime.timedelta(days=3)  # Fetch last 3 days
        start_date_str = start_date_dt.strftime("%Y-%m-%d")
        end_date_str = (today + datetime.timedelta(days=1)
                        ).strftime("%Y-%m-%d")

        # Fetch metadata for all potential cryptos (needed for symbols)
        crypto_data = fetch_coingecko_data()
        if not crypto_data:
            logger.warning(
                "No crypto metadata fetched from CoinGecko. Aborting delta sync.")
            return

        # Alternatively, fetch only symbols already in our DB?
        # session = Session()
        # try:
        #     existing_crypto_symbols = [a.symbol for a in session.query(CryptoAsset.symbol).all()]
        # finally:
        #     session.close()
        # crypto_data_filtered = [c for c in crypto_data if c.get('symbol','').upper() in existing_crypto_symbols]
        # Let's stick with fetching all metadata for simplicity, similar to full sync.

        historical_data = {}
        processed_count = 0
        for coin in crypto_data:
            coin_id = coin.get("id")
            symbol = coin.get("symbol", "").upper()
            if not coin_id or not symbol:
                continue

            binance_symbol = symbol + "USDT"
            logger.debug(
                f"Fetching delta history for crypto: {binance_symbol} (ID: {coin_id})")

            df = fetch_binance_crypto_data(
                binance_symbol, start_date_str, end_date_str)
            if df is not None:
                historical_data[coin_id] = df
                logger.debug(
                    f"Fetched {len(df)} delta records for {binance_symbol}")
            else:
                logger.error(
                    f"Failed to fetch delta historical data for {binance_symbol}")

            processed_count += 1
            time.sleep(REQUEST_DELAY_SECONDS)

        update_crypto_asset_and_quote(
            crypto_data, historical_data, upsert=True)
        _sync_common_update_state(sync_type="delta")
        logger.info("Global Delta Sync for Cryptocurrencies Completed.")
    except Exception as e:
        logger.error(
            f"Global Delta Sync for Cryptos Failed: {e}\n{traceback.format_exc()}")


def full_sync_currency(ticker=None):
    if ticker:
        logger.info(f"Starting Full Sync for Currency: {ticker}...")
    else:
        logger.info("Starting Global Full Sync for Currencies...")

    try:
        currency_list = get_currency_list()  # Get codes and names
        if ticker:
            currency_list = [
                (code, name) for code, name in currency_list if code.upper() == ticker.upper()]
            if not currency_list:
                logger.error(f"Ticker '{ticker}' not found in currency list.")
                raise ValueError(f"Currency ticker '{ticker}' not found")

        if not currency_list:
            logger.warning("No currencies found to sync.")
            return

        historical_data = {}
        for currency_code, _ in currency_list:
            logger.debug(
                f"Fetching full FX history for currency: {currency_code}")

            if currency_code.upper() == "USD":
                # Create dummy data for USD -> USD rate = 1
                date_range = pd.date_range(
                    start=HISTORICAL_START_DATE, end=datetime.datetime.now().date(), freq='D')
                df = pd.DataFrame(1.0, index=date_range, columns=[
                                  "Open", "High", "Low", "Close"])
                historical_data[currency_code] = df
                logger.debug(f"Generated dummy history for USD.")
            else:
                df = fetch_fx_daily_data(
                    currency_code, "USD", outputsize="full")  # Fetch full history
                if df is None:  # Error occurred during fetch
                    logger.error(
                        f"Failed to fetch FX daily data for {currency_code}/USD")
                    # Should we skip or raise? Let's skip this currency.
                    continue
                elif df.empty:
                    logger.warning(
                        f"Empty historical data returned for {currency_code}/USD")

                historical_data[currency_code] = df
                logger.debug(
                    f"Fetched {len(df)} records for {currency_code}/USD")

            # Respect AlphaVantage rate limits (can be strict, e.g., 5/min)
            time.sleep(15)  # Sleep longer for AV free tier

        update_currency_asset_and_quote(
            currency_list, historical_data, upsert=True)  # Use upsert=True
        _sync_common_update_state(sync_type="full")
        if ticker:
            logger.info(f"Full Sync for Currency {ticker} Completed.")
        else:
            logger.info("Global Full Sync for Currencies Completed.")
    except Exception as e:
        logger.error(
            f"Currency Full Sync Failed: {e}\n{traceback.format_exc()}")


def delta_sync_currency(ticker=None):
    if ticker:
        logger.info(f"Starting Delta Sync for Currency: {ticker}...")
    else:
        logger.info("Starting Global Delta Sync for Currencies...")

    try:
        today = datetime.datetime.now().date()
        # Fetch compact data which usually covers recent days for delta
        outputsize = "compact"

        currency_list = get_currency_list()
        if ticker:
            currency_list = [
                (code, name) for code, name in currency_list if code.upper() == ticker.upper()]
            if not currency_list:
                logger.error(f"Ticker '{ticker}' not found in currency list.")
                raise ValueError(f"Currency ticker '{ticker}' not found")

        if not currency_list:
            logger.warning("No currencies found for delta sync.")
            return

        historical_data = {}
        for currency_code, _ in currency_list:
            logger.debug(
                f"Fetching delta FX history for currency: {currency_code}")

            if currency_code.upper() == "USD":
                # Generate dummy data for the last few days
                date_range = pd.date_range(
                    end=today, periods=3, freq='D')  # Just a few days
                df = pd.DataFrame(1.0, index=date_range, columns=[
                                  "Open", "High", "Low", "Close"])
                historical_data[currency_code] = df
                logger.debug(f"Generated dummy delta history for USD.")
            else:
                df = fetch_fx_daily_data(
                    currency_code, "USD", outputsize=outputsize)
                if df is None:
                    logger.error(
                        f"Failed to fetch delta FX daily data for {currency_code}/USD")
                    continue
                elif df.empty:
                    logger.warning(
                        f"Empty delta historical data returned for {currency_code}/USD")

                historical_data[currency_code] = df
                logger.debug(
                    f"Fetched {len(df)} delta records for {currency_code}/USD")

            time.sleep(15)  # Rate limit

        update_currency_asset_and_quote(
            currency_list, historical_data, upsert=True)
        _sync_common_update_state(sync_type="delta")
        if ticker:
            logger.info(f"Delta Sync for Currency {ticker} Completed.")
        else:
            logger.info("Global Delta Sync for Currencies Completed.")
    except Exception as e:
        logger.error(
            f"Currency Delta Sync Failed: {e}\n{traceback.format_exc()}")


# --- Cache Refresh Functions ---

def refresh_stock_top_n_tickers(query_counter, top_n, delay_t):
    """Refreshes the cache for the most frequently queried stock tickers."""
    logger.debug(f"Refreshing cache for top {top_n} stock tickers...")
    session = Session()
    try:
        # Correctly extract tickers (t[0]) where asset_type (t[1]) is 'STOCK'
        top_stock_keys = [t[0] for t, count in query_counter.most_common(
            top_n * 2) if t[1] == "STOCK"][:top_n]  # Get more initially, filter, then limit

        if not top_stock_keys:
            logger.debug(
                "No stock tickers found in query counter for cache refresh.")
            return

        # Find the corresponding AssetQuotes to get the source_ticker used by yFinance
        asset_quotes = session.query(AssetQuote).filter(
            AssetQuote.ticker.in_(top_stock_keys),
            AssetQuote.from_asset_type == "STOCK"  # Ensure it's a stock quote
        ).all()

        # Unique source tickers
        source_tickers = list(
            set(aq.source_ticker for aq in asset_quotes if aq.source_ticker))

        if not source_tickers:
            logger.debug("No source tickers found for top stock keys.")
            return

        logger.debug(
            f"Found {len(source_tickers)} unique source tickers to refresh: {source_tickers}")

        prices = StockDataSource.refresh_latest_prices(source_tickers)
        now = datetime.datetime.now()
        ds_name = "YFINANCE"  # Assuming yFinance is the source for stocks
        refreshed_count = 0
        not_found_count = 0

        for st in source_tickers:
            price_result = prices.get(st)
            key = (ds_name, st)
            if price_result == "NOT_FOUND":
                # Use specific TTL for not found
                expires = now + datetime.timedelta(minutes=NOT_FOUND_TTL)
                latest_cache[key] = (price_result, now, expires)
                not_found_count += 1
            elif isinstance(price_result, (int, float)):
                expires = now + datetime.timedelta(minutes=REGULAR_TTL)
                latest_cache[key] = (price_result, now, expires)
                refreshed_count += 1
            else:
                logger.warning(
                    f"Received unexpected price result '{price_result}' for {st} during cache refresh.")

        logger.info(
            f"Stock cache refresh: Updated {refreshed_count} tickers, marked {not_found_count} as NOT_FOUND.")
        # time.sleep(delay_t) # Delay might not be needed if refresh_latest_prices handles it internally

    except Exception as e:
        logger.error(
            f"Error refreshing top N stock tickers cache: {e}\n{traceback.format_exc()}")
    finally:
        session.close()


def refresh_crypto_prices():
    """Refreshes the cache for all crypto prices from Binance."""
    logger.debug("Refreshing cache for crypto prices...")
    try:
        # This method already updates latest_cache internally
        prices = CryptoDataSource.get_all_latest_prices()
        logger.info(
            f"Crypto cache refresh: Updated {len(prices)} tickers from Binance.")
    except Exception as e:
        logger.error(
            f"Error refreshing crypto prices cache: {e}\n{traceback.format_exc()}")


def refresh_currency_prices():
    """Refreshes the cache for currency prices from AlphaVantage."""
    logger.debug("Refreshing cache for currency prices...")
    try:
        currency_list = get_currency_list()
        # Get only codes
        codes = [code for code, name in currency_list if code]
        if not codes:
            logger.warning("No currency codes found to refresh.")
            return

        # CurrencyDataSource.refresh_latest_prices calls get_latest_price repeatedly,
        # which handles caching internally.
        prices = CurrencyDataSource.refresh_latest_prices(codes)
        updated_count = sum(1 for p in prices.values()
                            if p != "NOT_FOUND" and p is not None)
        not_found_count = sum(1 for p in prices.values() if p == "NOT_FOUND")
        logger.info(
            f"Currency cache refresh: Updated {updated_count} currencies, marked {not_found_count} as NOT_FOUND.")
    except Exception as e:
        logger.error(
            f"Error refreshing currency prices cache: {e}\n{traceback.format_exc()}")


def refresh_all_latest_prices():
    """Main scheduled job to refresh caches for top stocks, crypto, and currencies."""
    start_time = time.time()
    logger.info("Starting scheduled cache refresh cycle...")
    from utils import query_counter  # Import here to ensure it's the loaded counter

    refresh_stock_top_n_tickers(
        query_counter, TOP_N_TICKERS, REQUEST_DELAY_SECONDS)
    refresh_crypto_prices()
    # refresh_currency_prices() # This is now handled by a separate, less frequent job by default

    # Update the global timestamp
    # Use importlib.reload if cache_storage might be modified elsewhere unexpectedly
    # Or pass the timestamp back if needed
    global last_cache_refresh
    last_cache_refresh = datetime.datetime.now()

    duration = time.time() - start_time
    logger.info(
        f"Cache refresh cycle completed in {duration:.2f} seconds. Last refresh set to: {last_cache_refresh}")

# --- fetch_yf_data modification to accept ticker_list ---


def fetch_yf_data(max_tickers_per_request, delay_t, query, start_date=HISTORICAL_START_DATE, end_date=None, sample_size=None, ticker_list=None):
    logger.info("Starting data fetch from yfinance...")
    all_quotes_list = []  # Store list of quote dicts

    if ticker_list:
        symbols = ticker_list
        logger.info(
            f"Fetching data for specific ticker list ({len(symbols)} tickers).")
        # Need to fetch info for these tickers to get quote data
        # yf.Tickers() is better for this than individual yf.Ticker() calls
        if symbols:
            yf_tickers = yf.Tickers(" ".join(symbols))
            for symbol in symbols:
                try:
                    info = yf_tickers.tickers.get(symbol).info
                    # Reconstruct a quote dict similar to screen output
                    quote = {
                        "symbol": symbol,
                        "longName": info.get("longName"),
                        "displayName": info.get("displayName"),
                        "language": info.get("language"),
                        "region": info.get("region"),
                        "quoteType": info.get("quoteType"),
                        "exchange": info.get("exchange"),
                        "fullExchangeName": info.get("fullExchangeName"),
                        "firstTradeDateEpochUtc": info.get("firstTradeDateEpochUtc")
                        # Add other relevant fields if needed
                    }
                    all_quotes_list.append(quote)
                except Exception as info_err:
                    logger.warning(
                        f"Could not fetch info for ticker {symbol}: {info_err}")
            quotes_df = pd.DataFrame(all_quotes_list)
        else:
            quotes_df = pd.DataFrame()  # Empty if no symbols

    elif query:
        logger.info(f"Fetching data using yfinance screen query.")
        offset = 0
        size = sample_size if sample_size is not None else 250  # Default screen size

        if sample_size is not None:
            result = yf.Tickers.screen(
                query, offset=0, size=sample_size)  # Use class method
            quotes = result.get("quotes", [])
            all_quotes_list.extend(quotes)
        else:
            while True:
                try:
                    result = yf.Tickers.screen(query, offset=offset, size=size)
                    quotes = result.get("quotes", [])
                    if not quotes:
                        break
                    all_quotes_list.extend(quotes)
                    offset += size
                    logger.debug(
                        f"Fetched {len(quotes)} quotes, total {offset}...")
                    time.sleep(0.5)  # Small delay between screen pages
                except Exception as screen_err:
                    logger.error(
                        f"Error during yfinance screen fetch at offset {offset}: {screen_err}")
                    break  # Stop fetching on error

        quotes_df = pd.DataFrame(all_quotes_list)
        symbols = quotes_df["symbol"].dropna().tolist()
    else:
        logger.error("fetch_yf_data requires either a query or a ticker_list.")
        return pd.DataFrame(), {}

    # --- Fetch Historical Data ---
    historical_data = {}
    symbols_to_download = quotes_df["symbol"].dropna().tolist()
    if not symbols_to_download:
        logger.warning("No symbols identified to download historical data.")
        return quotes_df, {}

    from utils import chunk_list  # Local import ok here
    logger.info(
        f"Downloading historical data for {len(symbols_to_download)} symbols...")
    for batch_symbols in chunk_list(symbols_to_download, max_tickers_per_request):
        tickers_str = " ".join(batch_symbols)
        try:
            data = yf.download(
                tickers=tickers_str,
                start=start_date,
                end=end_date,
                interval="1d",
                group_by='ticker',
                progress=False,  # Disable progress bar for cleaner logs
                timeout=30  # Add timeout
            )

            if data.empty:
                logger.warning(
                    f"No historical data returned for batch: {tickers_str}")
                continue

            # Handle MultiIndex vs single ticker response
            if isinstance(data.columns, pd.MultiIndex):
                # Iterate through tickers in the batch, check if data exists
                available_tickers_in_response = data.columns.get_level_values(
                    0).unique().tolist()
                for ticker in batch_symbols:
                    if ticker in available_tickers_in_response:
                        ticker_data = data[ticker].dropna(
                            how='all')  # Drop rows with all NaNs
                        if not ticker_data.empty:
                            historical_data[ticker] = ticker_data
                    # else: logger.debug(f"No data for {ticker} in multi-index response.")
            elif len(batch_symbols) == 1:
                # Single ticker response, DataFrame columns are OHLCV etc.
                ticker = batch_symbols[0]
                ticker_data = data.dropna(how='all')
                if not ticker_data.empty:
                    historical_data[ticker] = ticker_data
            else:
                # This case should ideally not happen with group_by='ticker'
                logger.warning(
                    f"Unexpected data structure returned by yf.download for batch: {tickers_str}")

            logger.debug(
                f"Downloaded batch ending with {batch_symbols[-1]}. Total historical series: {len(historical_data)}")

        except Exception as dl_err:
            logger.error(f"Error downloading batch '{tickers_str}': {dl_err}")
            # Mark tickers in this batch as failed? Or just skip? Skip for now.

        time.sleep(delay_t)  # Delay between batches

    logger.info(
        f"Finished historical data download. Fetched for {len(historical_data)} symbols.")
    return quotes_df, historical_data
