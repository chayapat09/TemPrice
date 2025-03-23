import datetime
import time
import pandas as pd
from decimal import Decimal
from collections import Counter
import os
import logging
from models import Session, QueryCount, CurrencyAsset
from sqlalchemy.exc import SQLAlchemyError

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

def prepopulate_currency_assets():
    currencies = [
        ("USD", "US Dollar"),
        ("THB", "Thai Baht"),
        ("SGD", "Singapore Dollar"),
        ("USDT", "Tether USD")
    ]
    session = Session()
    try:
        for symbol, name in currencies:
            asset = session.query(CurrencyAsset).filter_by(asset_type="CURRENCY", symbol=symbol).first()
            if not asset:
                asset_currency = CurrencyAsset(asset_type="CURRENCY", symbol=symbol, name=name)
                session.add(asset_currency)
        session.commit()
    except SQLAlchemyError as e:
        session.rollback()
        logger.error(f"Error prepopulating currency assets: {e}")
        raise
    finally:
        session.close()