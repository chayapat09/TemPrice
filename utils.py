import datetime
import time
import pandas as pd
from decimal import Decimal
from collections import Counter
import os
import logging
import csv
import re
import ast
import operator as op
from models import Session, AssetQuote, AssetOHLCV

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
        from models import QueryCount
        query_counts = session.query(QueryCount).all()
        for qc in query_counts:
            key = (qc.ticker, qc.asset_type)
            query_counter[key] = qc.count
            last_saved_counts[key] = qc.count
    except Exception as e:
        logger.error(f"Error loading query counter: {e}")
        raise
    finally:
        session.close()

def save_query_counter():
    session = Session()
    try:
        from models import QueryCount
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
    except Exception as e:
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
    from models import CurrencyAsset, CryptoAsset, Session
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
    except Exception as e:
        session.rollback()
        logger.error(f"Error prepopulating currency assets: {e}")
        raise
    finally:
        session.close()

# New utility functions for Derived Tickers

# Safe evaluation of arithmetic expressions using AST
allowed_operators = {
    ast.Add: op.add,
    ast.Sub: op.sub,
    ast.Mult: op.mul,
    ast.Div: op.truediv,
    ast.USub: op.neg
}

def safe_eval_expr(expr, context):
    """
    Safely evaluate an arithmetic expression with given context.
    Only allows basic arithmetic operations and variables from context.
    """
    node = ast.parse(expr, mode='eval')
    def eval_(node):
        if isinstance(node, ast.Expression):
            return eval_(node.body)
        elif isinstance(node, ast.Num):  # For Python <3.8
            return node.n
        elif isinstance(node, ast.Constant):  # For Python 3.8+
            return node.value
        elif isinstance(node, ast.BinOp):
            left = eval_(node.left)
            right = eval_(node.right)
            operator = allowed_operators.get(type(node.op))
            if operator is None:
                raise TypeError(f"Unsupported operator: {node.op}")
            return operator(left, right)
        elif isinstance(node, ast.UnaryOp):
            operand = eval_(node.operand)
            operator = allowed_operators.get(type(node.op))
            if operator is None:
                raise TypeError(f"Unsupported unary operator: {node.op}")
            return operator(operand)
        elif isinstance(node, ast.Name):
            if node.id in context:
                return context[node.id]
            else:
                raise ValueError(f"Unknown variable: {node.id}")
        else:
            raise TypeError(f"Unsupported expression: {node}")
    return eval_(node)

def extract_tickers(formula):
    """
    Extract ticker symbols from formula.
    Assumes ticker symbols are sequences of uppercase letters and digits that are not numbers.
    """
    tokens = re.findall(r"[A-Z0-9]+", formula)
    tickers = []
    for token in tokens:
        try:
            float(token)
        except ValueError:
            tickers.append(token)
    return list(set(tickers))

def get_historical_series(ticker):
    """
    Retrieve historical close price series for a given ticker from AssetOHLCV.
    Returns a dict mapping date (datetime.date) to close price.
    """
    session = Session()
    try:
        asset_quote = session.query(AssetQuote).filter_by(ticker=ticker).first()
        if asset_quote:
            records = session.query(AssetOHLCV).filter_by(asset_quote_id=asset_quote.id).all()
            series = { record.price_date.date(): float(record.close_price) for record in records if record.close_price is not None }
            return series
        return {}
    except Exception as e:
        logger.error(f"Error fetching historical series for {ticker}: {e}")
        return {}
    finally:
        session.close()

def get_latest_price_for_asset(ticker):
    """
    Retrieve the latest price for a given ticker by looking up AssetQuote.
    """
    session = Session()
    try:
        from data_fetchers import StockDataSource, CryptoDataSource, CurrencyDataSource
        asset_quote = session.query(AssetQuote).filter_by(ticker=ticker).first()
        if asset_quote:
            asset_type = asset_quote.from_asset_type.upper() if asset_quote.from_asset_type else None
            if asset_type == "STOCK":
                return StockDataSource.get_latest_price(asset_quote.source_ticker)
            elif asset_type == "CRYPTO":
                return CryptoDataSource.get_latest_price(asset_quote.source_ticker)
            elif asset_type == "CURRENCY":
                return CurrencyDataSource.get_latest_price(asset_quote.source_ticker)
        return None
    except Exception as e:
        logger.error(f"Error fetching latest price for {ticker}: {e}")
        return None
    finally:
        session.close()
