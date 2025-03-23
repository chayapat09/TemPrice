from flask import Flask, jsonify, request, render_template
import datetime
import os
import time
from collections import Counter
from apscheduler.schedulers.background import BackgroundScheduler
from models import Session, AssetQuote, AssetOHLCV, DeltaSyncState, Asset
from sync import full_sync_stocks, full_sync_crypto, delta_sync_stocks, delta_sync_crypto, refresh_all_latest_prices, latest_cache, last_cache_refresh
from utils import load_query_counter, save_query_counter, query_counter, prepopulate_currency_assets
import logging

logger = logging.getLogger(__name__)

app = Flask(__name__)
api_stats = Counter()

@app.before_request
def before_request():
    if request.path.startswith('/api/'):
        key = request.path + "_" + request.args.get("ticker", "") + "_" + request.args.get("asset_type", "STOCK").upper()
        api_stats[key] += 1

@app.route("/api/unified")
def get_unified_ticker():
    ticker = request.args.get("ticker")
    if not ticker:
        return jsonify({"error": "Ticker parameter is required"}), 400
    session = Session()
    try:
        asset_quote = session.query(AssetQuote).filter_by(ticker=ticker).first()
        if not asset_quote:
            return jsonify({"error": "Ticker not found"}), 404
        ohlcv_records = session.query(AssetOHLCV).filter_by(asset_quote_id=asset_quote.id).all()
        ds_key = (asset_quote.data_source.name.upper() if asset_quote.data_source else "UNKNOWN", asset_quote.source_ticker)
        cache_entry = latest_cache.get(ds_key, (None, None))
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
            "latest_cache": {
                "price": cache_entry[0],
                "timestamp": cache_entry[1].isoformat() if cache_entry[1] else None
            },
            "historical_data": [
                {
                    "date": record.price_date.isoformat(),
                    "open": float(record.open_price) if record.open_price is not None else None,
                    "high": float(record.high_price) if record.high_price is not None else None,
                    "low": float(record.low_price) if record.low_price is not None else None,
                    "close": float(record.close_price) if record.close_price is not None else None,
                    "volume": float(record.volume) if record.volume is not None else None,
                }
                for record in ohlcv_records
            ]
        }
        return jsonify(unified_data)
    except Exception as e:
        logger.error(f"Error fetching unified ticker data: {e}")
        return jsonify({"error": "Database error"}), 500
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
        data_quality_metrics = {
            "total_assets": total_assets,
            "total_asset_quotes": total_asset_quotes,
            "total_ohlcv_records": total_ohlcv,
            "missing_name_assets": missing_name_assets
        }
        return jsonify(data_quality_metrics)
    except Exception as e:
        logger.error(f"Error fetching data quality metrics: {e}")
        return jsonify({"error": "Database error"}), 500
    finally:
        session.close()

@app.route("/api/ticker_traffic")
def ticker_traffic():
    data = [{"ticker": t[1], "asset_type": t[0], "count": count} for t, count in query_counter.most_common()]
    return jsonify(data)

@app.route("/api/cache_info")
def cache_info():
    from apscheduler.schedulers.background import BackgroundScheduler
    scheduler = BackgroundScheduler()
    cache_job = scheduler.get_job("cache_refresh")
    if cache_job and cache_job.next_run_time:
        now_aware = datetime.datetime.now(tz=cache_job.next_run_time.tzinfo)
        diff_seconds = (cache_job.next_run_time - now_aware).total_seconds()
        next_cache_refresh = f"{int(diff_seconds // 60)} minutes" if diff_seconds >= 60 else f"{int(diff_seconds)} seconds"
    else:
        next_cache_refresh = "N/A"
    return jsonify({
        "last_cache_refresh": last_cache_refresh.isoformat() if last_cache_refresh else None,
        "next_cache_refresh": next_cache_refresh
    })

@app.route("/api/latest")
def get_latest():
    ticker = request.args.get("ticker")
    asset_type = request.args.get("asset_type", "STOCK").upper()
    if not ticker:
        return jsonify({"error": "Ticker parameter is required"}), 400
    session = Session()
    try:
        asset_quote = session.query(AssetQuote).filter_by(ticker=ticker).first()
        if asset_quote:
            ds_key = (asset_quote.data_source.name.upper() if asset_quote.data_source else "UNKNOWN", asset_quote.source_ticker)
        else:
            ds_key = (None, None)
    finally:
        session.close()
    timestamp = latest_cache.get(ds_key, (None, datetime.datetime.now()))[1]
    from data_fetchers import StockDataSource, CryptoDataSource
    result = None
    if asset_type == "STOCK":
        result = StockDataSource.get_latest_price(asset_quote.source_ticker) if asset_quote else "NOT_FOUND"
    else:
        result = CryptoDataSource.get_latest_price(asset_quote.source_ticker) if asset_quote else "NOT_FOUND"
    if isinstance(result, (int, float)):
        return jsonify({
            "ticker": ticker,
            "asset_type": asset_type,
            "price": result,
            "timestamp": timestamp.isoformat() if timestamp else None
        })
    elif result == "NOT_FOUND":
        return jsonify({"error": "Ticker not found"}), 404
    else:
        return jsonify({"error": "Unable to fetch latest price"}), 500

@app.route("/api/assets")
def get_assets():
    asset_type = request.args.get("asset_type", None)
    session = Session()
    try:
        if asset_type:
            assets = session.query(Asset).filter_by(asset_type=asset_type.upper()).all()
        else:
            assets = session.query(Asset).all()
        asset_list = [
            {
                "asset_type": asset.asset_type,
                "symbol": asset.symbol,
                "name": asset.name,
                "source_asset_key": asset.source_asset_key
            }
            for asset in assets
        ]
        return jsonify(asset_list)
    except Exception as e:
        logger.error(f"Error fetching assets: {e}")
        return jsonify({"error": "Database error"}), 500
    finally:
        session.close()

@app.route("/api/historical")
def get_historical():
    ticker = request.args.get("ticker")
    if not ticker:
        return jsonify({"error": "Ticker parameter is required"}), 400
    session = Session()
    try:
        asset_quote = session.query(AssetQuote).filter_by(ticker=ticker).first()
        if not asset_quote:
            return jsonify({"error": "No historical data found for ticker"}), 404
        records = session.query(AssetOHLCV).filter_by(asset_quote_id=asset_quote.id).all()
        data = [
            {
                "date": record.price_date.isoformat(),
                "open": float(record.open_price) if record.open_price is not None else None,
                "high": float(record.high_price) if record.high_price is not None else None,
                "low": float(record.low_price) if record.low_price is not None else None,
                "close": float(record.close_price) if record.close_price is not None else None,
                "volume": float(record.volume) if record.volume is not None else None,
            }
            for record in records
        ]
        return jsonify({"ticker": ticker, "historical_data": data})
    except Exception as e:
        logger.error(f"Error fetching historical data: {e}")
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
        from models import QueryCount
        query_counts_count = session.query(QueryCount).count()
        db_file = os.path.join('instance', 'stock_data.db')
        if os.path.exists(db_file):
            db_size = os.path.getsize(db_file) / (1024 * 1024)
            db_size_str = f"{db_size:.2f} MB" if db_size < 1024 else f"{db_size / 1024:.2f} GB"
        else:
            db_size_str = "Database file not found"
        stats = {
            "total_assets": total_assets,
            "total_asset_quotes": total_asset_quotes,
            "total_ohlcv_records": total_ohlcv,
            "db_size": db_size_str,
            "cache_hit_rate": "100%",
            "api_requests_24h": sum(api_stats.values()),
            "table_records": {
                "assets": total_assets,
                "asset_quotes": total_asset_quotes,
                "asset_ohlcv": total_ohlcv,
                "delta_sync_state": delta_sync_state_count,
                "query_counts": query_counts_count
            },
        }
        return jsonify(stats)
    except Exception as e:
        logger.error(f"Error fetching stats: {e}")
        return jsonify({"error": "Database error"}), 500
    finally:
        session.close()

@app.route("/api/tickers")
def get_tickers():
    query = request.args.get("query", "").strip().lower()
    if not query:
        return jsonify({"error": "Query parameter is required"}), 400

    asset_type = request.args.get("asset_type", None)
    try:
        limit = int(request.args.get("limit", 10))
        page = int(request.args.get("page", 1))
        from config import MAX_TICKERS_PER_REQUEST
        limit = min(limit, MAX_TICKERS_PER_REQUEST)
        offset = (page - 1) * limit
    except ValueError:
        return jsonify({"error": "Invalid pagination parameters"}), 400

    fuzzy_enabled = request.args.get("fuzzy", "false").lower() == "true"
    session = Session()
    try:
        from rapidfuzz import fuzz
        base_query = session.query(AssetQuote)
        if asset_type:
            base_query = base_query.filter(AssetQuote.from_asset_type == asset_type.upper())
        base_query = base_query.filter(
            (AssetQuote.ticker.ilike(f"%{query}%")) | (AssetQuote.source_ticker.ilike(f"%{query}%"))
        )
        if fuzzy_enabled:
            candidate_results = base_query.limit(50).all()
            scored_results = []
            for record in candidate_results:
                score = max(
                    fuzz.token_set_ratio(query, record.ticker.lower()),
                    fuzz.token_set_ratio(query, record.source_ticker.lower())
                )
                scored_results.append((score, record))
            scored_results.sort(key=lambda x: x[0], reverse=True)
            final_results = [record for _, record in scored_results[offset: offset + limit]]
        else:
            final_results = base_query.offset(offset).limit(limit).all()
        response = [
            {"ticker": r.ticker, "source_ticker": r.source_ticker}
            for r in final_results
        ]
        return jsonify(response)
    except Exception as e:
        logger.error(f"Error fetching tickers: {e}")
        return jsonify({"error": "Database error"}), 500
    finally:
        session.close()

@app.route("/api/sync/full", methods=["POST"])
def sync_full():
    data = request.get_json() or {}
    ticker = data.get("ticker")
    asset_type = data.get("asset_type", "STOCK").upper()
    data_source = data.get("data_source")
    if not data_source:
        data_source = "YFINANCE" if asset_type == "STOCK" else "BINANCE" if asset_type == "CRYPTO" else None
    try:
        if ticker:
            if asset_type == "STOCK":
                if data_source.upper() != "YFINANCE":
                    return jsonify({"error": "Invalid data source for STOCK. Supported: YFINANCE"}), 400
                from data_fetchers import fetch_yf_data_for_ticker
                quotes_df, historical_data = fetch_yf_data_for_ticker(ticker)
                if quotes_df is not None and historical_data is not None:
                    from sync import update_stock_asset_and_quote
                    update_stock_asset_and_quote(quotes_df, historical_data, upsert=True)
                    return jsonify({"message": f"Full sync for stock ticker {ticker} completed using {data_source}."})
                else:
                    return jsonify({"error": f"Failed to fetch data for stock ticker {ticker}"}), 404
            elif asset_type == "CRYPTO":
                if data_source.upper() != "BINANCE":
                    return jsonify({"error": "Invalid data source for CRYPTO. Supported: BINANCE"}), 400
                from data_fetchers import fetch_coingecko_data, fetch_binance_crypto_data
                coins = fetch_coingecko_data()
                coin_data = next((coin for coin in coins if coin.get("id", "").lower() == ticker.lower()), None)
                if coin_data:
                    symbol = coin_data["symbol"].upper() + "USDT"
                    historical_data = fetch_binance_crypto_data(symbol, "2020-01-01", None)
                    if historical_data is not None:
                        from sync import update_crypto_asset_and_quote
                        update_crypto_asset_and_quote([coin_data], {coin_data["id"]: historical_data}, upsert=True)
                        return jsonify({"message": f"Full sync for crypto ticker {ticker} completed using {data_source}."})
                    else:
                        return jsonify({"error": f"Failed to fetch historical data for crypto ticker {ticker}"}), 404
                else:
                    return jsonify({"error": f"Failed to fetch metadata for crypto ticker {ticker}"}), 404
            else:
                return jsonify({"error": "Invalid asset_type"}), 400
        else:
            if asset_type == "CRYPTO":
                full_sync_crypto()
                return jsonify({"message": "Global full sync for cryptocurrencies completed."})
            else:
                full_sync_stocks()
                return jsonify({"message": "Global full sync for stocks completed."})
    except Exception as e:
        logger.error(f"Error in full sync: {e}")
        return jsonify({"error": str(e)}), 500

@app.route("/api/sync/delta", methods=["POST"])
def sync_delta():
    data = request.get_json() or {}
    ticker = data.get("ticker")
    asset_type = data.get("asset_type", "STOCK").upper()
    data_source = data.get("data_source")
    if not data_source:
        data_source = "YFINANCE" if asset_type == "STOCK" else "BINANCE" if asset_type == "CRYPTO" else None
    try:
        if ticker:
            today = datetime.datetime.now().date()
            two_days_ago = today - datetime.timedelta(days=2)
            if asset_type == "STOCK":
                if data_source.upper() != "YFINANCE":
                    return jsonify({"error": "Invalid data source for STOCK. Supported: YFINANCE"}), 400
                from data_fetchers import fetch_yf_data_for_ticker
                quotes_df, historical_data = fetch_yf_data_for_ticker(ticker, start_date=two_days_ago.strftime("%Y-%m-%d"), end_date=today.strftime("%Y-%m-%d"))
                if quotes_df is not None and historical_data is not None:
                    from sync import update_stock_asset_and_quote
                    update_stock_asset_and_quote(quotes_df, historical_data, upsert=True)
                    return jsonify({"message": f"Delta sync for stock ticker {ticker} completed using {data_source}."})
                else:
                    return jsonify({"error": f"Failed to fetch delta data for stock ticker {ticker}"}), 404
            elif asset_type == "CRYPTO":
                if data_source.upper() != "BINANCE":
                    return jsonify({"error": "Invalid data source for CRYPTO. Supported: BINANCE"}), 400
                from data_fetchers import fetch_coingecko_data, fetch_binance_crypto_data
                coins = fetch_coingecko_data()
                coin_data = next((coin for coin in coins if coin.get("id", "").lower() == ticker.lower()), None)
                if coin_data:
                    symbol = coin_data["symbol"].upper() + "USDT"
                    historical_data = fetch_binance_crypto_data(symbol, two_days_ago.strftime("%Y-%m-%d"), today.strftime("%Y-%m-%d"))
                    if historical_data is not None:
                        from sync import update_crypto_asset_and_quote
                        update_crypto_asset_and_quote([coin_data], {coin_data["id"]: historical_data}, upsert=True)
                        return jsonify({"message": f"Delta sync for crypto ticker {ticker} completed using {data_source}."})
                    else:
                        return jsonify({"error": f"Failed to fetch delta historical data for crypto ticker {ticker}"}), 404
                else:
                    return jsonify({"error": f"Failed to fetch metadata for crypto ticker {ticker}"}), 404
            else:
                return jsonify({"error": "Invalid asset_type"}), 400
        else:
            if asset_type == "CRYPTO":
                delta_sync_crypto()
                return jsonify({"message": "Global delta sync for cryptocurrencies completed."})
            else:
                delta_sync_stocks()
                return jsonify({"message": "Global delta sync for stocks completed."})
    except Exception as e:
        logger.error(f"Error in delta sync: {e}")
        return jsonify({"error": str(e)}), 500

@app.route("/dashboard")
def dashboard():
    return render_template('dashboard.html')

if __name__ == "__main__":
    from models import Base, engine
    session = Session()
    try:
        assets_count = session.query(Asset).count()
        asset_quotes_count = session.query(AssetQuote).count()
        if assets_count == 0 or asset_quotes_count == 0:
            Base.metadata.drop_all(engine)
            Base.metadata.create_all(engine)
    except Exception as e:
        logger.error(f"Error checking database counts: {e}")
        raise
    finally:
        session.close()
    prepopulate_currency_assets()
    refresh_all_latest_prices()
    load_query_counter()
    from config import FLASK_HOST, FLASK_PORT, LATEST_CACHE_REFRESH_INTERVAL_MINUTES, DELTA_SYNC_INTERVAL_DAYS, QUERY_COUNTER_SAVE_INTERVAL_MINUTES
    scheduler = BackgroundScheduler()
    scheduler.add_job(refresh_all_latest_prices, "interval", minutes=LATEST_CACHE_REFRESH_INTERVAL_MINUTES, id="cache_refresh")
    scheduler.add_job(delta_sync_stocks, "interval", days=DELTA_SYNC_INTERVAL_DAYS, id="delta_sync_stocks")
    scheduler.add_job(delta_sync_crypto, "interval", days=DELTA_SYNC_INTERVAL_DAYS, id="delta_sync_crypto")
    scheduler.add_job(save_query_counter, "interval", minutes=QUERY_COUNTER_SAVE_INTERVAL_MINUTES, id="save_query_counter")
    scheduler.start()
    app.run(host=FLASK_HOST, port=FLASK_PORT)