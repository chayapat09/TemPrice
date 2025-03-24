from models import DerivedTicker, Session
from utils import safe_eval_expr, extract_tickers, get_historical_series, get_latest_price_for_asset
import datetime

class DerivedDataSource:
    @staticmethod
    def get_latest_price(ticker, visited=None):
        if visited is None:
            visited = set()
        if ticker in visited:
            raise ValueError("Circular reference detected in derived tickers")
        visited.add(ticker)
        
        session = Session()
        try:
            derived = session.query(DerivedTicker).filter_by(ticker=ticker).first()
        finally:
            session.close()
        
        if not derived:
            # Not a derived ticker – fall back to the base lookup.
            return get_latest_price_for_asset(ticker)
        
        # Derived ticker: evaluate its formula.
        underlying_tickers = extract_tickers(derived.formula)
        context = {}
        for ut in underlying_tickers:
            session = Session()
            try:
                dt = session.query(DerivedTicker).filter_by(ticker=ut).first()
            finally:
                session.close()
            if dt:
                price_ut = DerivedDataSource.get_latest_price(ut, visited)
            else:
                price_ut = get_latest_price_for_asset(ut)
            if price_ut in [None, "NOT_FOUND"]:
                raise ValueError(f"Latest price for underlying ticker {ut} not found")
            context[ut] = price_ut
        return safe_eval_expr(derived.formula, context)
    
    @staticmethod
    def get_historical_data(ticker, visited=None):
        if visited is None:
            visited = set()
        if ticker in visited:
            raise ValueError("Circular reference detected in historical derived ticker evaluation")
        visited.add(ticker)
        
        session = Session()
        try:
            derived = session.query(DerivedTicker).filter_by(ticker=ticker).first()
        finally:
            session.close()
        
        if not derived:
            return get_historical_series(ticker)
        
        underlying_tickers = extract_tickers(derived.formula)
        historical_series = {}
        for ut in underlying_tickers:
            session = Session()
            try:
                dt = session.query(DerivedTicker).filter_by(ticker=ut).first()
            finally:
                session.close()
            if dt:
                series = DerivedDataSource.get_historical_data(ut, visited)
            else:
                series = get_historical_series(ut)
            if not series:
                raise ValueError(f"Historical data for underlying ticker {ut} not found")
            historical_series[ut] = series
        # Find common dates across all underlying series.
        common_dates = set.intersection(*(set(data.keys()) for data in historical_series.values()))
        common_dates = sorted(common_dates)
        derived_series = {}
        for d in common_dates:
            context_day = {ut: historical_series[ut][d] for ut in underlying_tickers}
            try:
                value = safe_eval_expr(derived.formula, context_day)
            except Exception:
                value = None
            derived_series[d] = value
        return derived_series
