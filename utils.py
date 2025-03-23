import datetime
import time
import pandas as pd
from decimal import Decimal
from collections import Counter
import os
import logging
from models import CryptoAsset, Session, QueryCount, CurrencyAsset
from sqlalchemy.exc import SQLAlchemyError
import csv

logger = logging.getLogger(__name__)

def safe_convert(value, convert_func=lambda x: x):
    if value is None or pd.isna(value):
        return None
    try:
        return convert_func(value)
    except Exception:
        return None

def chunk_list(lst, chunk_size):
    for i in range(0, len(lst), chunk_size):
        yield lst[i:i + chunk_size]

# Global query counter and persistence functions
query_counter = Counter()
last_saved_counts = {}

def load_query_counter():
    session = Session()
    try:
        query_counts = session.query(QueryCount).all()
        for qc in query_counts:
            key = (qc.ticker, qc.asset_type)
            query_counter[key] = qc.count
            last_saved_counts[key] = qc.count
    except SQLAlchemyError as e:
        logger.error(f"Error loading query counter: {e}")
        raise
    finally:
        session.close()

def save_query_counter():
    session = Session()
    try:
        for (ticker, asset_type), current_count in query_counter.items():
            key = (ticker, asset_type)
            baseline = last_saved_counts.get(key, 0)
            delta = current_count - baseline
            if delta > 0:
                existing = session.query(QueryCount).filter_by(ticker=ticker, asset_type=asset_type).first()
                if existing:
                    existing.count += delta
                else:
                    session.add(QueryCount(ticker=ticker, asset_type=asset_type, count=current_count))
                last_saved_counts[key] = current_count
        session.commit()
    except SQLAlchemyError as e:
        session.rollback()
        logger.error(f"Error saving query counter: {e}")
        raise
    finally:
        session.close()

def get_currency_list():
    currency_list = []
    file_path = os.path.join("data", "physical_currency_list.csv")
    if os.path.exists(file_path):
        with open(file_path, newline='', encoding='utf-8') as csvfile:
            reader = csv.DictReader(csvfile)
            for row in reader:
                code = row.get("currency code") or row.get("Currency Code")
                name = row.get("currency name") or row.get("Currency Name")
                if code and name:
                    currency_list.append((code.strip().upper(), name.strip()))
    return currency_list

def prepopulate_currency_assets():
    currency_list = get_currency_list()
    session = Session()
    try:
        for currency_code, currency_name in currency_list:
            asset = session.query(CurrencyAsset).filter_by(asset_type="CURRENCY", symbol=currency_code).first()
            if not asset:
                asset_currency = CurrencyAsset(asset_type="CURRENCY", symbol=currency_code, name=currency_name, source_asset_key=currency_code)
                session.add(asset_currency)
        usdt_asset = session.query(CryptoAsset).filter_by(asset_type="CRYPTO", symbol="USDT").first()
        if not usdt_asset:
            asset_crypto = CryptoAsset(asset_type="CRYPTO", symbol="USDT", name="USD Tether", source_asset_key="tether")
            session.add(asset_crypto)

        session.commit()
    except SQLAlchemyError as e:
        session.rollback()
        logger.error(f"Error prepopulating currency assets: {e}")
        raise
    finally:
        session.close()