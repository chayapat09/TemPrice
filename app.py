import re
from config import HISTORICAL_START_DATE
from flask import Flask, jsonify, request, render_template
import datetime
import os
import time
from collections import Counter
from apscheduler.schedulers.background import BackgroundScheduler
from models import Session, AssetQuote, AssetOHLCV, DeltaSyncState, Asset, DerivedTicker
from sync import full_sync_stocks, full_sync_crypto, delta_sync_stocks, delta_sync_crypto, full_sync_currency, delta_sync_currency, refresh_all_latest_prices, refresh_currency_prices
from cache_storage import latest_cache, last_cache_refresh
from utils import load_query_counter, save_query_counter, query_counter, prepopulate_currency_assets, safe_convert, safe_eval_expr, extract_tickers # Added safe_convert, safe_eval_expr, extract_tickers
import logging
from data_fetchers import StockDataSource, CryptoDataSource, CurrencyDataSource
from derived_datasource import DerivedDataSource
from sqlalchemy.exc import SQLAlchemyError
import traceback
logger = logging.getLogger(__name__) # Use __name__
api_stats = Counter()
app = Flask(__name__) # Use __name__

# Initialize scheduler globally but after app creation
scheduler = BackgroundScheduler()

@app.before_request
def before_request():
    if request.path.startswith('/api/'):
        # Use a safer key format, handling potential missing args
        ticker_arg = request.args.get("ticker", "")
        asset_type_arg = request.args.get("asset_type", "STOCK").upper()
        key = f"{request.path}|{ticker_arg}|{asset_type_arg}"
        api_stats[key] += 1

@app.route("/api/unified")
def get_unified_ticker():
    ticker = request.args.get("ticker")
    if not ticker:
        return jsonify({"error": "Ticker parameter is required"}), 400

    session = Session()
    try:
        asset_quote = session.query(AssetQuote).filter_by(ticker=ticker).first()

        if asset_quote:
            ohlcv_records = session.query(AssetOHLCV).filter_by(asset_quote_id=asset_quote.id).order_by(AssetOHLCV.price_date).all() # Ensure order
            ds_key = (asset_quote.data_source.name.upper() if asset_quote.data_source else "UNKNOWN", asset_quote.source_ticker)

            # Use the DataSource method to get the latest price (handles caching internally)
            latest_price_result = None
            if asset_quote.from_asset_type == "STOCK":
                 latest_price_result = StockDataSource.get_latest_price(asset_quote.source_ticker)
            elif asset_quote.from_asset_type == "CRYPTO":
                 latest_price_result = CryptoDataSource.get_latest_price(asset_quote.source_ticker)
            elif asset_quote.from_asset_type == "CURRENCY":
                 latest_price_result = CurrencyDataSource.get_latest_price(asset_quote.source_ticker)

            # Get cache timestamp if entry exists
            cache_entry = latest_cache.get(ds_key)
            cache_timestamp = cache_entry[1].isoformat() if cache_entry and cache_entry[1] else None
            latest_price = latest_price_result if isinstance(latest_price_result, (int, float)) else None

            unified_data = {
                "ticker": asset_quote.ticker,
                "source_ticker": asset_quote.source_ticker,
                "data_source": asset_quote.data_source.name if asset_quote.data_source else None,
                "from_asset": {
                    "asset_type": asset_quote.from_asset_type,
                    "symbol": asset_quote.from_asset_symbol,
                },
                "to_asset": {
                    "asset_type": asset_quote.to_asset_type,
                    "symbol": asset_quote.to_asset_symbol,
                },
                "latest_price": latest_price, # Use the result from DataSource
                "latest_cache_timestamp": cache_timestamp, # Timestamp from cache
                "historical_data": [
                    {
                        "date": record.price_date.isoformat(),
                        "open": safe_convert(record.open_price, float),
                        "high": safe_convert(record.high_price, float),
                        "low": safe_convert(record.low_price, float),
                        "close": safe_convert(record.close_price, float),
                        "volume": safe_convert(record.volume, float),
                        "value": safe_convert(record.close_price, float) # Standardized value field
                    }
                    for record in ohlcv_records
                ]
            }
            return jsonify(unified_data)
        else:
            # Use DerivedDataSource for derived tickers.
            derived = session.query(DerivedTicker).filter_by(ticker=ticker).first()
            if not derived:
                return jsonify({"error": "Ticker not found"}), 404

            latest_price = None
            latest_context = {} # For debugging/info
            try:
                # Use the method that also returns context for preview/debugging
                latest_price, latest_context = DerivedDataSource.get_latest_price_with_context(ticker)
            except Exception as e:
                logger.error(f"Error evaluating derived formula for {ticker}: {e}\n{traceback.format_exc()}")
                return jsonify({"error": f"Error evaluating formula: {str(e)}"}), 500

            historical_series = {}
            try:
                historical_series = DerivedDataSource.get_historical_data(ticker)
            except Exception as e:
                logger.error(f"Error fetching historical data for derived ticker {ticker}: {e}\n{traceback.format_exc()}")
                # Return empty historical data instead of failing the whole request
                historical_series = {}

            historical_data = [
                {
                    "date": d.isoformat(),
                    "open": None, # Add null fields for consistency
                    "high": None,
                    "low": None,
                    "close": value, # Use close for consistency with chart expectations? or keep 'value'? Let's use 'value'.
                    "volume": None,
                    "value": value
                 }
                for d, value in historical_series.items()
            ]

            unified_data = {
                "ticker": derived.ticker,
                "formula": derived.formula,
                "asset_type": "DERIVED",
                "latest_price": latest_price,
                "latest_context": latest_context, # Include context for info
                "latest_cache_timestamp": datetime.datetime.now().isoformat(), # Derived is calculated now
                "historical_data": historical_data
            }
            return jsonify(unified_data)

    except Exception as e:
        logger.error(f"Error fetching unified ticker data for {ticker}: {e}\n{traceback.format_exc()}")
        return jsonify({"error": "An internal error occurred"}), 500
    finally:
        session.close()


@app.route("/api/data_quality")
def data_quality():
    session = Session()
    try:
        total_assets = session.query(Asset).count()
        total_asset_quotes = session.query(AssetQuote).count()
        total_ohlcv = session.query(AssetOHLCV).count()
        missing_name_assets = session.query(Asset).filter(Asset.name.is_(None)).count()

        # Add more metrics maybe?
        # e.g., assets without any quotes, quotes without recent OHLCV data

        data_quality_metrics = {
            "total_assets": total_assets,
            "total_asset_quotes": total_asset_quotes,
            "total_ohlcv_records": total_ohlcv,
            "missing_name_assets": missing_name_assets
            # Add more metrics here
        }
        return jsonify(data_quality_metrics)
    except Exception as e:
        logger.error(f"Error fetching data quality metrics: {e}\n{traceback.format_exc()}")
        return jsonify({"error": "Database error"}), 500
    finally:
        session.close()

@app.route("/api/ticker_traffic")
def ticker_traffic():
    # Note: Uses the in-memory query_counter which resets on app restart
    data = [{"ticker": t[0], "asset_type": t[1], "count": count} for t, count in query_counter.most_common()]
    return jsonify(data)

@app.route("/api/cache_info")
def cache_info():
    # Access the globally defined scheduler
    global scheduler
    try:
        cache_job = scheduler.get_job("cache_refresh") if scheduler.running else None
        next_cache_refresh_str = "Scheduler not running"
        if cache_job and cache_job.next_run_time:
            # Make sure timezone comparison is handled correctly
            now_aware = datetime.datetime.now(cache_job.next_run_time.tzinfo)
            if cache_job.next_run_time > now_aware:
                diff_seconds = (cache_job.next_run_time - now_aware).total_seconds()
                if diff_seconds >= 60:
                    next_cache_refresh_str = f"in {int(diff_seconds // 60)} min {int(diff_seconds % 60)} sec"
                else:
                    next_cache_refresh_str = f"in {int(diff_seconds)} seconds"
            else:
                 next_cache_refresh_str = "Next run time is in the past (job might be running or delayed)"
        elif cache_job:
            next_cache_refresh_str = "Job exists but no next run time scheduled (may be paused or finished)"
        else:
            next_cache_refresh_str = "Job 'cache_refresh' not found or scheduler stopped"

    except Exception as e:
        logger.error(f"Error getting scheduler info: {e}")
        next_cache_refresh_str = "Error fetching next refresh time"

    return jsonify({
        "last_cache_refresh": last_cache_refresh.isoformat() if last_cache_refresh else "N/A",
        "next_cache_refresh": next_cache_refresh_str,
        "cache_size": len(latest_cache) # Add cache size
    })


@app.route("/api/latest")
def get_latest():
    ticker = request.args.get("ticker")
    asset_type = request.args.get("asset_type", "STOCK").upper() # Default remains STOCK

    if not ticker:
        return jsonify({"error": "Ticker parameter is required"}), 400

    # Update query counter for latest endpoint
    # Consider moving this logic if it causes issues with concurrent requests
    query_counter[(ticker, asset_type)] += 1

    session = Session() # Keep session for AssetQuote lookup needed for non-derived
    try:
        if asset_type == "DERIVED":
            session.close() # Not needed for derived evaluation itself
            derived = session.query(DerivedTicker).filter_by(ticker=ticker).first() # Need session again briefly
            session.close() # Close after query
            if not derived:
                return jsonify({"error": "Derived ticker not found"}), 404
            try:
                # Use the simpler get_latest_price here, context not needed for this endpoint
                result = DerivedDataSource.get_latest_price(ticker)
                if result == "NOT_FOUND" or result is None: # Handle cases where underlying data is missing
                    return jsonify({"error": f"Could not evaluate formula, underlying data missing for {ticker}"}), 404
                return jsonify({
                    "ticker": ticker,
                    "asset_type": "DERIVED",
                    "price": result,
                    "formula": derived.formula,
                    "timestamp": datetime.datetime.now().isoformat() # Timestamp of calculation
                })
            except ValueError as ve: # Catch specific evaluation errors like circular refs or missing data
                 logger.warning(f"Evaluation error for derived ticker {ticker}: {ve}")
                 return jsonify({"error": f"Error evaluating formula: {str(ve)}"}), 500
            except Exception as e:
                logger.error(f"Unexpected error evaluating derived formula for {ticker}: {e}\n{traceback.format_exc()}")
                return jsonify({"error": f"Unexpected error evaluating formula: {str(e)}"}), 500

        else: # Handle STOCK, CRYPTO, CURRENCY
            asset_quote = session.query(AssetQuote).filter_by(ticker=ticker).first()
            if not asset_quote:
                return jsonify({"error": "Ticker definition not found in AssetQuote"}), 404

            # Determine correct DataSource method based on AssetQuote's from_asset_type
            source_ticker = asset_quote.source_ticker
            actual_asset_type = asset_quote.from_asset_type.upper()
            data_source_name = asset_quote.data_source.name.upper() if asset_quote.data_source else "UNKNOWN"

            result = None
            if actual_asset_type == "STOCK":
                result = StockDataSource.get_latest_price(source_ticker)
            elif actual_asset_type == "CRYPTO":
                result = CryptoDataSource.get_latest_price(source_ticker)
            elif actual_asset_type == "CURRENCY":
                result = CurrencyDataSource.get_latest_price(source_ticker)
            else:
                return jsonify({"error": f"Unsupported asset type '{actual_asset_type}' found for ticker '{ticker}'"}), 500

            if result == "NOT_FOUND":
                 return jsonify({"error": f"Latest price not found via {data_source_name} for source ticker {source_ticker}"}), 404
            elif isinstance(result, (int, float)):
                # Fetch timestamp from cache if available
                ds_key = (data_source_name, source_ticker)
                cache_entry = latest_cache.get(ds_key)
                timestamp = cache_entry[1].isoformat() if cache_entry and cache_entry[1] else datetime.datetime.now().isoformat() # Fallback timestamp

                return jsonify({
                    "ticker": ticker,
                    "asset_type": actual_asset_type, # Return the actual type from AssetQuote
                    "price": result,
                    "timestamp": timestamp
                })
            else: # Should ideally not happen if NOT_FOUND is handled, but acts as a fallback
                logger.error(f"Unexpected result type '{type(result)}' for {ticker} from {data_source_name}")
                return jsonify({"error": "Unable to fetch latest price due to an unexpected error"}), 500

    except Exception as e:
        logger.error(f"Generic error in /api/latest for {ticker} ({asset_type}): {e}\n{traceback.format_exc()}")
        return jsonify({"error": "An internal server error occurred"}), 500
    finally:
        if session.is_active:
            session.close()


@app.route("/api/historical")
def get_historical():
    ticker = request.args.get("ticker")
    asset_type_param = request.args.get("asset_type", None) # Don't default, determine from DB or derived
    if not ticker:
        return jsonify({"error": "Ticker parameter is required"}), 400

    session = Session()
    try:
        # Check if it's a derived ticker first
        derived = session.query(DerivedTicker).filter_by(ticker=ticker).first()
        if derived:
            # Update query counter for historical endpoint (DERIVED)
            query_counter[(ticker, "DERIVED")] += 1
            session.close() # Close session before potentially long calculation

            historical_series = {}
            try:
                historical_series = DerivedDataSource.get_historical_data(ticker)
            except ValueError as ve: # Catch specific evaluation errors
                 logger.warning(f"Historical evaluation error for derived ticker {ticker}: {ve}")
                 return jsonify({"error": f"Error evaluating derived historical data: {str(ve)}"}), 500
            except Exception as e:
                logger.error(f"Error fetching historical data for derived ticker {ticker}: {e}\n{traceback.format_exc()}")
                return jsonify({"error": f"Error evaluating derived historical data: {str(e)}"}), 500

            historical_data = [
                 {
                    "date": d.isoformat(),
                    "open": None,
                    "high": None,
                    "low": None,
                    "close": value, # Keeping 'close' might simplify chart logic, use value? Use value.
                    "volume": None,
                    "value": value # Standardized value field
                 }
                 for d, value in historical_series.items()
            ]
            # Sort by date ascending
            historical_data.sort(key=lambda x: x['date'])

            return jsonify({
                "ticker": ticker,
                "asset_type": "DERIVED",
                "formula": derived.formula,
                "historical_data": historical_data
            })

        else: # Not a derived ticker, look in AssetQuote
            asset_quote = session.query(AssetQuote).filter_by(ticker=ticker).first()
            if not asset_quote:
                return jsonify({"error": "Ticker not found"}), 404

            actual_asset_type = asset_quote.from_asset_type.upper()
            # Update query counter for historical endpoint (non-derived)
            query_counter[(ticker, actual_asset_type)] += 1

            records = session.query(AssetOHLCV).filter_by(asset_quote_id=asset_quote.id).order_by(AssetOHLCV.price_date).all() # Ensure order

            if not records:
                 return jsonify({"warning": "Ticker found but no historical OHLCV data available", "ticker": ticker, "historical_data": []}), 200 # Return 200 with empty data? Or 404? Let's use 200 OK with empty list.


            historical_data = [
                {
                    "date": record.price_date.isoformat(),
                    "open": safe_convert(record.open_price, float),
                    "high": safe_convert(record.high_price, float),
                    "low": safe_convert(record.low_price, float),
                    "close": safe_convert(record.close_price, float),
                    "volume": safe_convert(record.volume, float),
                    "value": safe_convert(record.close_price, float) # Standardized value field
                }
                for record in records
            ]
            return jsonify({
                "ticker": ticker,
                "asset_type": actual_asset_type, # Use actual type
                "historical_data": historical_data
            })

    except Exception as e:
        logger.error(f"Error fetching historical data for {ticker}: {e}\n{traceback.format_exc()}")
        return jsonify({"error": "Database error fetching historical data"}), 500
    finally:
        if session.is_active:
            session.close()


@app.route("/api/assets")
def get_assets():
    asset_type = request.args.get("asset_type", None)
    session = Session()
    try:
        query = session.query(Asset)
        if asset_type:
            query = query.filter(Asset.asset_type == asset_type.upper())

        assets = query.order_by(Asset.asset_type, Asset.symbol).all()

        asset_list = [
            {
                "asset_type": asset.asset_type,
                "symbol": asset.symbol,
                "name": asset.name,
                "source_asset_key": asset.source_asset_key
                # Consider adding more specific fields based on polymorphic type if needed
            }
            for asset in assets
        ]
        return jsonify(asset_list)
    except Exception as e:
        logger.error(f"Error fetching assets: {e}\n{traceback.format_exc()}")
        return jsonify({"error": "Database error"}), 500
    finally:
        session.close()

@app.route("/api/stats")
def get_stats():
    session = Session()
    try:
        total_assets = session.query(Asset).count()
        total_asset_quotes = session.query(AssetQuote).count()
        total_ohlcv = session.query(AssetOHLCV).count()
        delta_sync_state_count = session.query(DeltaSyncState).count()
        derived_ticker_count = session.query(DerivedTicker).count() # Added

        # QueryCount needs explicit import if not already imported
        from models import QueryCount
        query_counts_count = session.query(QueryCount).count()

        db_file = os.path.join('instance', 'stock_data.db') # Assuming default location
        db_size_str = "N/A"
        try:
            if os.path.exists(db_file):
                db_size_bytes = os.path.getsize(db_file)
                if db_size_bytes < 1024 * 1024:
                    db_size_str = f"{db_size_bytes / 1024:.2f} KB"
                elif db_size_bytes < 1024 * 1024 * 1024:
                    db_size_str = f"{db_size_bytes / (1024 * 1024):.2f} MB"
                else:
                    db_size_str = f"{db_size_bytes / (1024 * 1024 * 1024):.2f} GB"
            else:
                db_size_str = "Database file not found"
        except Exception as size_e:
             logger.error(f"Could not get DB size: {size_e}")
             db_size_str = "Error reading size"

        stats = {
            "total_assets": total_assets,
            "total_asset_quotes": total_asset_quotes,
            "total_ohlcv_records": total_ohlcv,
            "total_derived_tickers": derived_ticker_count, # Added
            "db_size": db_size_str,
            # "cache_hit_rate": "Not Tracked", # Removed misleading 100%
            "api_requests_total_runtime": sum(api_stats.values()), # Clarified label
            "table_records": {
                "assets": total_assets,
                "asset_quotes": total_asset_quotes,
                "asset_ohlcv": total_ohlcv,
                "derived_tickers": derived_ticker_count, # Added
                "delta_sync_state": delta_sync_state_count,
                "query_counts": query_counts_count
            },
        }
        return jsonify(stats)
    except Exception as e:
        logger.error(f"Error fetching stats: {e}\n{traceback.format_exc()}")
        return jsonify({"error": "Database error fetching stats"}), 500
    finally:
        session.close()

@app.route("/api/tickers")
def get_tickers():
    query = request.args.get("query", "").strip().lower()
    if not query:
        # Allow empty query to list some tickers? Or require it? Let's require it.
        return jsonify({"error": "Query parameter is required"}), 400

    asset_type = request.args.get("asset_type", None) # Allow filtering by type
    try:
        limit = int(request.args.get("limit", 10))
        page = int(request.args.get("page", 1))
        # from config import MAX_TICKERS_PER_REQUEST # Maybe enforce a max limit server-side?
        # limit = min(limit, MAX_TICKERS_PER_REQUEST)
        offset = (page - 1) * limit
    except ValueError:
        return jsonify({"error": "Invalid pagination parameters (limit, page must be integers)"}), 400

    fuzzy_enabled = request.args.get("fuzzy", "false").lower() == "true"

    session = Session()
    try:
        from sqlalchemy import or_
        from rapidfuzz import fuzz, process # Use process for efficiency with choices

        results_to_score = []
        asset_type_filter = asset_type.upper() if asset_type else None

        # Query AssetQuotes
        if not asset_type_filter or asset_type_filter != "DERIVED":
            aq_base_query = session.query(AssetQuote)
            if asset_type_filter:
                 # This filters based on the *primary* asset type (e.g., STOCK for TSLAUSD)
                 aq_base_query = aq_base_query.filter(AssetQuote.from_asset_type == asset_type_filter)

            if not fuzzy_enabled:
                 # Direct ILIKE search for non-fuzzy
                 aq_filter = or_(
                     AssetQuote.ticker.ilike(f"%{query}%"),
                     AssetQuote.source_ticker.ilike(f"%{query}%"),
                     # Consider searching Asset.name via join? Might be slow.
                 )
                 results_to_score.extend(aq_base_query.filter(aq_filter).all())
            else:
                 # For fuzzy, fetch a larger candidate pool based on a simpler filter first
                 # Increase candidate limit for better fuzzy results
                 candidate_limit = 100
                 aq_filter = or_(
                     AssetQuote.ticker.ilike(f"%{query[:2]}%"), # Match first few chars
                     AssetQuote.source_ticker.ilike(f"%{query[:2]}%"),
                 )
                 results_to_score.extend(aq_base_query.filter(aq_filter).limit(candidate_limit).all())


        # Query DerivedTickers
        if not asset_type_filter or asset_type_filter == "DERIVED":
            dt_base_query = session.query(DerivedTicker)
            if not fuzzy_enabled:
                 dt_filter = DerivedTicker.ticker.ilike(f"%{query}%")
                 results_to_score.extend(dt_base_query.filter(dt_filter).all())
            else:
                candidate_limit = 100
                dt_filter = DerivedTicker.ticker.ilike(f"%{query[:2]}%")
                results_to_score.extend(dt_base_query.filter(dt_filter).limit(candidate_limit).all())

        # Deduplicate results before scoring (in case same ticker appears multiple times)
        unique_results = {r.ticker: r for r in results_to_score}.values()


        # Score and sort results
        scored_results = []
        choices_map = {} # Map choice string back to original record

        if fuzzy_enabled:
            for record in unique_results:
                 if isinstance(record, AssetQuote):
                     # Create unique choice strings for fuzzy matching
                     choice_str_ticker = f"AQ_TICKER_{record.ticker}"
                     choice_str_source = f"AQ_SOURCE_{record.source_ticker}"
                     choices_map[choice_str_ticker] = record
                     choices_map[choice_str_source] = record
                 elif isinstance(record, DerivedTicker):
                     choice_str = f"DT_{record.ticker}"
                     choices_map[choice_str] = record

            # Use rapidfuzz.process.extract to find best matches
            extracted = process.extract(query, list(choices_map.keys()), scorer=fuzz.token_set_ratio, limit=offset + limit) # Fetch enough for pagination

            # Map extracted results back to records and store scores
            temp_results_map = {}
            for choice_str, score, _ in extracted:
                 record = choices_map[choice_str]
                 if record.ticker not in temp_results_map or score > temp_results_map[record.ticker][0]:
                     temp_results_map[record.ticker] = (score, record)

            # Sort by score descending
            final_scored = sorted(temp_results_map.values(), key=lambda x: x[0], reverse=True)
            final_results = [record for score, record in final_scored][offset : offset + limit]

        else:
            # Simple alphabetical sort for non-fuzzy
            # Need to handle AssetQuote vs DerivedTicker having different attributes for sorting
            def sort_key(r):
                t = r.ticker if hasattr(r, 'ticker') else ''
                return t.lower()

            unique_results = sorted(list(unique_results), key=sort_key)
            final_results = unique_results[offset : offset + limit]


        # Build uniform response
        response = []
        for record in final_results:
            if isinstance(record, AssetQuote):
                response.append({
                    "ticker": record.ticker,
                    "source_ticker": record.source_ticker,
                    "asset_type": record.from_asset_type, # Base asset type
                    # Add name maybe? Requires join or separate query.
                    # "name": record.from_asset.name if record.from_asset else None
                })
            elif isinstance(record, DerivedTicker):
                response.append({
                    "ticker": record.ticker,
                    "source_ticker": None, # Derived has no source ticker
                    "asset_type": "DERIVED",
                    "formula": record.formula,
                    # "name": record.ticker # Name is just the ticker for derived
                })

        return jsonify(response)

    except Exception as e:
        logger.error(f"Error fetching tickers for query '{query}': {e}\n{traceback.format_exc()}")
        return jsonify({"error": "Database error fetching tickers"}), 500
    finally:
        session.close()


# --- Sync Endpoints ---
# Mostly unchanged, but ensure they use the updated sync functions if those were modified.
@app.route("/api/sync/full", methods=["POST"])
def sync_full():
    data = request.get_json() or {}
    ticker = data.get("ticker") # Can be stock symbol, crypto ID, currency code
    asset_type = data.get("asset_type", "STOCK").upper()
    data_source = data.get("data_source") # Optional, defaults based on asset_type

    # Determine default data source if not provided
    if not data_source:
        if asset_type == "STOCK":
            data_source = "YFINANCE"
        elif asset_type == "CRYPTO":
            # Note: Crypto sync uses CoinGecko for metadata and Binance for OHLCV
            # We'll use "BINANCE" as the effective source for consistency here
            data_source = "BINANCE"
        elif asset_type == "CURRENCY":
            data_source = "ALPHAVANTAGE" # Corrected case
        else:
            data_source = None # Let the specific logic handle errors

    logger.info(f"Received full sync request: Ticker={ticker}, AssetType={asset_type}, DataSource={data_source}")

    try:
        if ticker: # Sync specific ticker
            if asset_type == "STOCK":
                if not data_source or data_source.upper() != "YFINANCE":
                    return jsonify({"error": "Invalid data source for STOCK. Supported: YFINANCE"}), 400
                # Use dedicated fetch function
                from data_fetchers import fetch_yf_data_for_ticker
                from sync import update_stock_asset_and_quote
                quotes_df, historical_data = fetch_yf_data_for_ticker(ticker, start_date=HISTORICAL_START_DATE) # Use config start date
                if historical_data: # Check if historical data was fetched
                    update_stock_asset_and_quote(quotes_df, historical_data, upsert=False) # Full sync = no upsert? Let's allow upsert=True for simplicity. It overwrites.
                    return jsonify({"message": f"Full sync initiated for stock ticker {ticker} using {data_source}."})
                else:
                    return jsonify({"error": f"Failed to fetch data for stock ticker {ticker} from {data_source}"}), 404

            elif asset_type == "CRYPTO":
                 # NOTE: Syncing a single crypto requires fetching its metadata first (CoinGecko)
                 # then its historical data (Binance). The `ticker` here refers to the CoinGecko ID.
                if not data_source or data_source.upper() != "BINANCE": # Even though metadata is from CG, OHLCV is Binance
                    return jsonify({"error": "Invalid data source for CRYPTO. Supported: BINANCE (for OHLCV)"}), 400

                from data_fetchers import fetch_coingecko_data, fetch_binance_crypto_data
                from sync import update_crypto_asset_and_quote
                from config import REQUEST_DELAY_SECONDS

                coins = fetch_coingecko_data() # Fetch metadata for lookup
                time.sleep(REQUEST_DELAY_SECONDS) # Avoid immediate rate limit

                coin_data = next((coin for coin in coins if coin.get("id", "").lower() == ticker.lower()), None)

                if not coin_data:
                    return jsonify({"error": f"Metadata not found for crypto ID '{ticker}' on CoinGecko"}), 404

                binance_symbol = coin_data.get("symbol", "").upper() + "USDT" # Assume USDT pair
                historical_df = fetch_binance_crypto_data(binance_symbol, HISTORICAL_START_DATE, None)

                if historical_df is not None: # Can be empty DataFrame if no data, but not None on error
                    # Need to wrap single coin data correctly for the update function
                    update_crypto_asset_and_quote([coin_data], {ticker: historical_df}, upsert=True)
                    return jsonify({"message": f"Full sync initiated for crypto ID {ticker} (Symbol: {binance_symbol}) using CoinGecko/Binance."})
                else:
                    # fetch_binance_crypto_data might return None on error or empty DF
                     # Check if it was an error or just no data
                     # Let's assume failure means error for simplicity here
                    return jsonify({"error": f"Failed to fetch historical data for {binance_symbol} from Binance"}), 404


            elif asset_type == "CURRENCY":
                if not data_source or data_source.upper() != "ALPHAVANTAGE":
                    return jsonify({"error": "Invalid data source for CURRENCY. Supported: AlphaVantage"}), 400
                # Call the specific currency sync function from sync.py
                full_sync_currency(ticker=ticker) # Pass the specific ticker
                return jsonify({"message": f"Full sync initiated for currency ticker {ticker} using {data_source}."})

            else:
                return jsonify({"error": "Invalid asset_type for specific sync"}), 400

        else: # Global sync for the specified asset type
            if asset_type == "STOCK":
                # Consider running this in background? For now, run synchronously.
                full_sync_stocks()
                return jsonify({"message": "Global full sync for stocks initiated."})
            elif asset_type == "CRYPTO":
                full_sync_crypto()
                return jsonify({"message": "Global full sync for cryptocurrencies initiated."})
            elif asset_type == "CURRENCY":
                full_sync_currency()
                return jsonify({"message": "Global full sync for currencies initiated."})
            else:
                # Default to stocks if asset_type is invalid/missing for global sync?
                # Let's require a valid type or default to STOCK.
                 logger.warning(f"Invalid asset_type '{asset_type}' for global sync, defaulting to STOCK.")
                 full_sync_stocks()
                 return jsonify({"message": "Global full sync for stocks initiated (defaulted)."})

    except ValueError as ve: # Catch specific errors like ticker not found in lists
        logger.warning(f"Value error during sync: {ve}")
        return jsonify({"error": str(ve)}), 400
    except Exception as e:
        logger.error(f"Error in full sync endpoint: {e}\n{traceback.format_exc()}")
        return jsonify({"error": f"An unexpected error occurred during sync: {str(e)}"}), 500


@app.route("/api/sync/delta", methods=["POST"])
def sync_delta():
    data = request.get_json() or {}
    ticker = data.get("ticker")
    asset_type = data.get("asset_type", "STOCK").upper()
    data_source = data.get("data_source")

    if not data_source:
        if asset_type == "STOCK":
            data_source = "YFINANCE"
        elif asset_type == "CRYPTO":
            data_source = "BINANCE" # Effective source for OHLCV
        elif asset_type == "CURRENCY":
            data_source = "ALPHAVANTAGE"
        else:
            data_source = None

    logger.info(f"Received delta sync request: Ticker={ticker}, AssetType={asset_type}, DataSource={data_source}")

    try:
        today = datetime.datetime.now().date()
        # Fetch slightly more data to handle potential gaps or timezone issues
        start_date_dt = today - datetime.timedelta(days=3) # Go back 3 days
        start_date_str = start_date_dt.strftime("%Y-%m-%d")
        end_date_str = (today + datetime.timedelta(days=1)).strftime("%Y-%m-%d") # Include today's potential data

        if ticker: # Delta sync specific ticker
            if asset_type == "STOCK":
                if not data_source or data_source.upper() != "YFINANCE":
                    return jsonify({"error": "Invalid data source for STOCK. Supported: YFINANCE"}), 400
                from data_fetchers import fetch_yf_data_for_ticker
                from sync import update_stock_asset_and_quote
                # Fetch only recent data
                quotes_df, historical_data = fetch_yf_data_for_ticker(ticker, start_date=start_date_str, end_date=end_date_str)
                if historical_data:
                    update_stock_asset_and_quote(quotes_df, historical_data, upsert=True) # Delta sync must upsert
                    return jsonify({"message": f"Delta sync initiated for stock ticker {ticker} using {data_source}."})
                else:
                    return jsonify({"error": f"Failed to fetch delta data for stock ticker {ticker} from {data_source}"}), 404

            elif asset_type == "CRYPTO":
                if not data_source or data_source.upper() != "BINANCE":
                    return jsonify({"error": "Invalid data source for CRYPTO. Supported: BINANCE (for OHLCV)"}), 400

                from data_fetchers import fetch_coingecko_data, fetch_binance_crypto_data
                from sync import update_crypto_asset_and_quote
                from config import REQUEST_DELAY_SECONDS

                # Still need metadata lookup for the symbol
                coins = fetch_coingecko_data()
                time.sleep(REQUEST_DELAY_SECONDS)
                coin_data = next((coin for coin in coins if coin.get("id", "").lower() == ticker.lower()), None)

                if not coin_data:
                    return jsonify({"error": f"Metadata not found for crypto ID '{ticker}' on CoinGecko"}), 404

                binance_symbol = coin_data.get("symbol", "").upper() + "USDT"
                # Fetch recent data
                historical_df = fetch_binance_crypto_data(binance_symbol, start_date_str, end_date_str)

                if historical_df is not None:
                    update_crypto_asset_and_quote([coin_data], {ticker: historical_df}, upsert=True)
                    return jsonify({"message": f"Delta sync initiated for crypto ID {ticker} (Symbol: {binance_symbol}) using CoinGecko/Binance."})
                else:
                    return jsonify({"error": f"Failed to fetch delta historical data for {binance_symbol} from Binance"}), 404

            elif asset_type == "CURRENCY":
                 if not data_source or data_source.upper() != "ALPHAVANTAGE":
                    return jsonify({"error": "Invalid data source for CURRENCY. Supported: AlphaVantage"}), 400
                 # Call the specific currency delta sync function
                 delta_sync_currency(ticker=ticker)
                 return jsonify({"message": f"Delta sync initiated for currency ticker {ticker} using {data_source}."})

            else:
                return jsonify({"error": "Invalid asset_type for specific delta sync"}), 400

        else: # Global delta sync
            if asset_type == "STOCK":
                delta_sync_stocks()
                return jsonify({"message": "Global delta sync for stocks initiated."})
            elif asset_type == "CRYPTO":
                delta_sync_crypto()
                return jsonify({"message": "Global delta sync for cryptocurrencies initiated."})
            elif asset_type == "CURRENCY":
                delta_sync_currency()
                return jsonify({"message": "Global delta sync for currencies initiated."})
            else:
                 logger.warning(f"Invalid asset_type '{asset_type}' for global delta sync, defaulting to STOCK.")
                 delta_sync_stocks()
                 return jsonify({"message": "Global delta sync for stocks initiated (defaulted)."})

    except ValueError as ve:
        logger.warning(f"Value error during delta sync: {ve}")
        return jsonify({"error": str(ve)}), 400
    except Exception as e:
        logger.error(f"Error in delta sync endpoint: {e}\n{traceback.format_exc()}")
        return jsonify({"error": f"An unexpected error occurred during delta sync: {str(e)}"}), 500


# --- Endpoints for managing Derived Tickers ---

# GET List derived tickers
@app.route("/api/derived", methods=["GET"])
def list_derived_tickers():
    session = Session()
    try:
        tickers = session.query(DerivedTicker).order_by(DerivedTicker.ticker).all()
        data = [{"ticker": dt.ticker, "formula": dt.formula} for dt in tickers]
        return jsonify(data)
    except Exception as e:
        logger.error(f"Error listing derived tickers: {e}\n{traceback.format_exc()}")
        return jsonify({"error": "Database error"}), 500
    finally:
        session.close()

# POST Create derived ticker
@app.route("/api/derived", methods=["POST"])
def create_derived_ticker():
    data = request.get_json() or {}
    ticker = data.get("ticker", "").strip()
    formula = data.get("formula", "").strip()

    if not ticker or not formula:
        return jsonify({"error": "Ticker and formula are required"}), 400

    # Basic validation (more robust validation happens on eval)
    if not re.match(r"^[A-Z0-9._-]+$", ticker): # Allow letters, numbers, dot, underscore, hyphen
         return jsonify({"error": "Ticker contains invalid characters. Use A-Z, 0-9, ., _, -"}), 400

    session = Session()
    try:
        # Check if ticker conflicts with existing AssetQuote ticker
        quote_exists = session.query(AssetQuote).filter_by(ticker=ticker).first()
        if quote_exists:
             return jsonify({"error": f"Ticker '{ticker}' is already used by a standard asset quote."}), 400

        # Check if derived ticker already exists
        exists = session.query(DerivedTicker).filter_by(ticker=ticker).first()
        if exists:
            return jsonify({"error": f"Derived ticker '{ticker}' already exists"}), 409 # Conflict

        # Attempt a basic evaluation to catch syntax errors early
        try:
            underlying = extract_tickers(formula)
            # Use dummy context for syntax check
            dummy_context = {ut: 1 for ut in underlying}
            safe_eval_expr(formula, dummy_context)
        except Exception as eval_err:
            return jsonify({"error": f"Formula validation failed: {str(eval_err)}"}), 400

        dt = DerivedTicker(ticker=ticker, formula=formula)
        session.add(dt)
        session.commit()
        logger.info(f"Created derived ticker: {ticker} = {formula}")
        return jsonify({"message": f"Derived ticker '{ticker}' created successfully."}), 201 # Created
    except SQLAlchemyError as e:
        session.rollback()
        logger.error(f"Error creating derived ticker '{ticker}': {e}\n{traceback.format_exc()}")
        # Check for specific constraint errors if needed
        return jsonify({"error": "Database error during creation"}), 500
    except Exception as e: # Catch other unexpected errors
        session.rollback()
        logger.error(f"Unexpected error creating derived ticker '{ticker}': {e}\n{traceback.format_exc()}")
        return jsonify({"error": "An unexpected error occurred"}), 500
    finally:
        session.close()


# PUT Update derived ticker (using path parameter)
@app.route("/api/derived/<string:ticker>", methods=["PUT"])
def update_derived_ticker(ticker):
    data = request.get_json() or {}
    formula = data.get("formula", "").strip()

    if not formula:
        return jsonify({"error": "Formula is required"}), 400

    session = Session()
    try:
        dt = session.query(DerivedTicker).filter_by(ticker=ticker).first()
        if not dt:
            return jsonify({"error": "Derived ticker not found"}), 404

        # Validate the new formula
        try:
            underlying = extract_tickers(formula)
            dummy_context = {ut: 1 for ut in underlying}
            safe_eval_expr(formula, dummy_context)
        except Exception as eval_err:
            return jsonify({"error": f"New formula validation failed: {str(eval_err)}"}), 400

        dt.formula = formula
        session.commit()
        logger.info(f"Updated derived ticker: {ticker} = {formula}")
        return jsonify({"message": f"Derived ticker '{ticker}' updated successfully."})
    except SQLAlchemyError as e:
        session.rollback()
        logger.error(f"Error updating derived ticker '{ticker}': {e}\n{traceback.format_exc()}")
        return jsonify({"error": "Database error during update"}), 500
    except Exception as e:
        session.rollback()
        logger.error(f"Unexpected error updating derived ticker '{ticker}': {e}\n{traceback.format_exc()}")
        return jsonify({"error": "An unexpected error occurred"}), 500
    finally:
        session.close()

# DELETE Derived ticker (using path parameter)
@app.route("/api/derived/<string:ticker>", methods=["DELETE"])
def delete_derived_ticker(ticker):
    session = Session()
    try:
        dt = session.query(DerivedTicker).filter_by(ticker=ticker).first()
        if not dt:
            return jsonify({"error": "Derived ticker not found"}), 404

        session.delete(dt)
        session.commit()
        logger.info(f"Deleted derived ticker: {ticker}")
        # Return 204 No Content or 200 OK with message? Let's use 200 OK.
        return jsonify({"message": f"Derived ticker '{ticker}' deleted successfully."})
    except SQLAlchemyError as e:
        session.rollback()
        logger.error(f"Error deleting derived ticker '{ticker}': {e}\n{traceback.format_exc()}")
        return jsonify({"error": "Database error during deletion"}), 500
    except Exception as e:
        session.rollback()
        logger.error(f"Unexpected error deleting derived ticker '{ticker}': {e}\n{traceback.format_exc()}")
        return jsonify({"error": "An unexpected error occurred"}), 500
    finally:
        session.close()

# POST Preview derived ticker formula evaluation
@app.route("/api/derived/preview", methods=["POST"])
def preview_derived_ticker():
    data = request.get_json() or {}
    formula = data.get("formula", "").strip()

    if not formula:
        return jsonify({"error": "Formula is required"}), 400

    try:
        # Extract underlying tickers from the formula provided
        underlying_tickers = extract_tickers(formula)
        if not underlying_tickers:
             return jsonify({"warning": "Formula contains no recognized ticker symbols."}), 200 # Not an error, but maybe useless

        # Fetch latest prices for underlying tickers (using DerivedDataSource to handle nested derived tickers)
        context = {}
        missing_tickers = []
        for ut in underlying_tickers:
             try:
                 # Important: Use the recursive get_latest_price from DerivedDataSource
                 # This handles cases where a derived ticker depends on another derived ticker.
                 price_ut = DerivedDataSource.get_latest_price(ut)
                 if price_ut in [None, "NOT_FOUND"]:
                     missing_tickers.append(ut)
                 else:
                     context[ut] = price_ut
             except ValueError as ve: # Catch errors from underlying fetches (e.g., circular ref)
                 logger.warning(f"Error fetching underlying price for '{ut}' during preview: {ve}")
                 return jsonify({"error": f"Error fetching underlying price for '{ut}': {str(ve)}"}), 400
             except Exception as fetch_err:
                 logger.error(f"Unexpected error fetching underlying price for '{ut}': {fetch_err}\n{traceback.format_exc()}")
                 return jsonify({"error": f"Server error fetching price for '{ut}'"}), 500

        if missing_tickers:
            return jsonify({"error": f"Could not fetch latest price for underlying ticker(s): {', '.join(missing_tickers)}"}), 404

        # Evaluate the formula with the fetched context
        result = safe_eval_expr(formula, context)

        return jsonify({
            "formula": formula,
            "context": context,
            "result": result
        })

    except ValueError as ve: # Catch errors from safe_eval_expr or ticker extraction
         logger.warning(f"Error during derived preview evaluation for formula '{formula}': {ve}")
         return jsonify({"error": f"Evaluation error: {str(ve)}"}), 400
    except Exception as e:
        logger.error(f"Unexpected error during derived preview for formula '{formula}': {e}\n{traceback.format_exc()}")
        return jsonify({"error": f"An unexpected error occurred during preview: {str(e)}"}), 500
    # No session needed here as it delegates price fetching


# --- HTML Templates ---
@app.route("/derived_ticker_manager")
def derived_ticker_manager():
    return render_template('derived_ticker_manager.html')

@app.route("/dashboard")
def dashboard():
    return render_template('dashboard.html')

@app.route("/")
def home():
    # Redirect root to dashboard
    return render_template('dashboard.html') # Or redirect('/dashboard')

# --- Main Execution ---
if __name__ == "__main__":
    from models import Base, engine

    # --- Database Initialization Check ---
    # This logic seems risky (dropping all tables if one count is zero).
    # Consider a more robust migration strategy (e.g., using Alembic).
    # For now, keep it but add more logging.
    session = Session()
    try:
        assets_count = session.query(Asset).count()
        asset_quotes_count = session.query(AssetQuote).count()
        logger.info(f"DB Check: Assets={assets_count}, AssetQuotes={asset_quotes_count}")
        # WARNING: This will WIPE the database if it exists but is empty or partially populated.
        # Only enable this if you understand the consequences.
        # if assets_count == 0 or asset_quotes_count == 0:
        # 	 logger.warning("Asset or AssetQuote count is zero. Recreating all tables.")
        # 	 Base.metadata.drop_all(engine)
        # 	 Base.metadata.create_all(engine)
        # else:
        #     logger.info("Database tables seem populated. Skipping recreation.")
        Base.metadata.create_all(engine) # Ensure tables exist without dropping
    except Exception as db_init_e:
        logger.error(f"CRITICAL: Error during database initialization check: {db_init_e}\n{traceback.format_exc()}")
        raise # Stop the application if DB check fails severely
    finally:
        session.close()

    # --- Prepopulate & Initial Refresh ---
    try:
        prepopulate_currency_assets() # Ensure USD, USDT etc. exist
        logger.info("Attempting initial cache refresh...")
        refresh_all_latest_prices() # Populate cache on startup
        logger.info("Initial cache refresh completed.")
        load_query_counter() # Load historical query counts
        logger.info(f"Loaded query counter with {len(query_counter)} items.")
    except Exception as startup_e:
         logger.error(f"Error during startup data population/refresh: {startup_e}\n{traceback.format_exc()}")
         # Decide if this is critical enough to stop startup

    # --- Scheduler Setup ---
    from config import (FLASK_HOST, FLASK_PORT,
                        LATEST_CACHE_REFRESH_INTERVAL_MINUTES,
                        DELTA_SYNC_INTERVAL_DAYS,
                        QUERY_COUNTER_SAVE_INTERVAL_MINUTES,
                        CURRENCY_CACHE_REFRESH_INTERVAL_MINUTES)

    # Use the globally defined scheduler
    # global scheduler
    try:
        # Add jobs with error handling (e.g., misfire_grace_time)
        scheduler.add_job(refresh_all_latest_prices, "interval", minutes=LATEST_CACHE_REFRESH_INTERVAL_MINUTES, id="cache_refresh", misfire_grace_time=60)
        scheduler.add_job(delta_sync_stocks, "interval", days=DELTA_SYNC_INTERVAL_DAYS, id="delta_sync_stocks", misfire_grace_time=3600)
        scheduler.add_job(delta_sync_crypto, "interval", days=DELTA_SYNC_INTERVAL_DAYS, id="delta_sync_crypto", misfire_grace_time=3600)
        scheduler.add_job(delta_sync_currency, "interval", days=DELTA_SYNC_INTERVAL_DAYS, id="delta_sync_currency", misfire_grace_time=3600) # Add delta sync for currency
        scheduler.add_job(save_query_counter, "interval", minutes=QUERY_COUNTER_SAVE_INTERVAL_MINUTES, id="save_query_counter", misfire_grace_time=60)
        # The separate currency refresh might be redundant if refresh_all_latest_prices includes it, but keep for now as per config
        scheduler.add_job(refresh_currency_prices, "interval", minutes=CURRENCY_CACHE_REFRESH_INTERVAL_MINUTES, id="currency_cache_refresh", misfire_grace_time=1800)

        scheduler.start()
        logger.info("Background scheduler started.")

        # Graceful shutdown
        import atexit
        atexit.register(lambda: scheduler.shutdown())
        atexit.register(lambda: save_query_counter()) # Save counters on exit

    except Exception as sched_e:
         logger.error(f"CRITICAL: Failed to start scheduler: {sched_e}\n{traceback.format_exc()}")
         # Decide whether to proceed without the scheduler

    # --- Run Flask App ---
    logger.info(f"Starting Flask app on {FLASK_HOST}:{FLASK_PORT}")
    app.run(host=FLASK_HOST, port=FLASK_PORT, use_reloader=False) # use_reloader=False is important for APScheduler