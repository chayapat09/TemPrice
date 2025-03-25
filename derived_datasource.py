from models import DerivedTicker, Session, AssetQuote # Added AssetQuote
from utils import safe_eval_expr, extract_tickers, get_historical_series, get_latest_price_for_asset
import datetime
import logging
import traceback # For detailed error logging

logger = logging.getLogger(__name__)

class DerivedDataSource:
    """
    Handles fetching latest and historical data for derived tickers by evaluating
    their formulas based on underlying asset data. Includes circular reference detection.
    """

    @staticmethod
    def get_latest_price(ticker, visited=None):
        """
        Recursively gets the latest price for a ticker.
        If the ticker is derived, evaluates its formula.
        If not derived, calls get_latest_price_for_asset.
        Handles circular references.
        Returns price (float/int) or "NOT_FOUND".
        """
        if visited is None:
            visited = set()

        # Check for circular reference BEFORE database query
        if ticker in visited:
            logger.error(f"Circular reference detected involving derived ticker: {ticker} in chain {visited}")
            raise ValueError(f"Circular reference detected involving: {ticker}")
        visited.add(ticker) # Add current ticker to visited path

        logger.debug(f"Getting latest price for: {ticker} (Visited: {visited})")

        session = Session()
        try:
            # Is it a derived ticker?
            derived = session.query(DerivedTicker).filter_by(ticker=ticker).first()

            if derived:
                # Derived ticker: extract underlying tickers and evaluate formula
                logger.debug(f"'{ticker}' is derived. Formula: {derived.formula}")
                underlying_tickers = extract_tickers(derived.formula)
                context = {}
                missing_underlying = []

                for ut in underlying_tickers:
                    try:
                        # Recursively call get_latest_price for underlying tickers
                        price_ut = DerivedDataSource.get_latest_price(ut, visited.copy()) # Pass copy of visited set
                        if price_ut == "NOT_FOUND" or price_ut is None:
                             logger.warning(f"Latest price not found for underlying ticker '{ut}' needed by '{ticker}'")
                             missing_underlying.append(ut)
                        else:
                             context[ut] = price_ut
                    except ValueError as e: # Catch circular refs or other errors from recursion
                         logger.error(f"Error getting price for underlying ticker '{ut}': {e}")
                         raise ValueError(f"Failed to get price for underlying ticker '{ut}': {str(e)}") # Propagate error

                if missing_underlying:
                     raise ValueError(f"Missing latest price for underlying ticker(s): {', '.join(missing_underlying)}")

                # Evaluate the formula using the fetched context
                try:
                    result = safe_eval_expr(derived.formula, context)
                    logger.debug(f"Evaluated '{ticker}': {derived.formula} with context {context} -> {result}")
                    return result
                except (ValueError, TypeError) as eval_err:
                    logger.error(f"Evaluation error for derived ticker '{ticker}' ({derived.formula}) with context {context}: {eval_err}\n{traceback.format_exc()}")
                    raise ValueError(f"Formula evaluation error: {str(eval_err)}") # Raise specific error

            else:
                # Not a derived ticker – fall back to the base asset lookup
                logger.debug(f"'{ticker}' is not derived. Looking up base asset price.")
                # Ensure the base ticker actually exists in AssetQuote before fetching
                quote_exists = session.query(AssetQuote.ticker).filter_by(ticker=ticker).first()
                if not quote_exists:
                     logger.warning(f"Ticker '{ticker}' not found in DerivedTickers or AssetQuotes.")
                     return "NOT_FOUND"

                session.close() # Close session before calling base fetcher
                return get_latest_price_for_asset(ticker) # Returns price or "NOT_FOUND"

        finally:
            if session.is_active:
                session.close()
            # Remove current ticker from visited set when returning up the stack
            # This line was missing, crucial for non-circular paths involving the same ticker later
            if ticker in visited:
                 visited.remove(ticker)


    @staticmethod
    def get_latest_price_with_context(ticker, visited=None):
        """
        Similar to get_latest_price but also returns the context used for evaluation.
        Useful for debugging/preview. Returns (price, context) or raises error.
        """
        if visited is None:
            visited = set()
        if ticker in visited:
            raise ValueError(f"Circular reference detected involving: {ticker}")
        visited.add(ticker)

        logger.debug(f"Getting latest price with context for: {ticker} (Visited: {visited})")

        session = Session()
        try:
            derived = session.query(DerivedTicker).filter_by(ticker=ticker).first()
            if not derived:
                # Base asset - context is just its own price (or empty if not found)
                session.close() # Close before calling base fetcher
                price = get_latest_price_for_asset(ticker)
                if price == "NOT_FOUND":
                     raise ValueError(f"Base ticker '{ticker}' not found")
                return price, {ticker: price}

            # Derived ticker
            logger.debug(f"'{ticker}' is derived. Formula: {derived.formula}")
            underlying_tickers = extract_tickers(derived.formula)
            context = {}
            missing_underlying = []

            for ut in underlying_tickers:
                try:
                    # Use get_latest_price for recursion here, context isn't needed from deeper levels for eval
                    price_ut = DerivedDataSource.get_latest_price(ut, visited.copy())
                    if price_ut == "NOT_FOUND" or price_ut is None:
                         missing_underlying.append(ut)
                    else:
                         context[ut] = price_ut
                except ValueError as e:
                     logger.error(f"Error getting price for underlying ticker '{ut}' (context): {e}")
                     raise ValueError(f"Failed to get price for underlying '{ut}': {str(e)}")

            if missing_underlying:
                 raise ValueError(f"Missing latest price for underlying ticker(s): {', '.join(missing_underlying)}")

            try:
                result = safe_eval_expr(derived.formula, context)
                logger.debug(f"Evaluated (context) '{ticker}': {derived.formula} -> {result}")
                return result, context # Return result and the context used
            except (ValueError, TypeError) as eval_err:
                logger.error(f"Evaluation error (context) for '{ticker}': {eval_err}")
                raise ValueError(f"Formula evaluation error: {str(eval_err)}")

        finally:
            if session.is_active:
                session.close()
            if ticker in visited:
                 visited.remove(ticker)


    @staticmethod
    def get_historical_data(ticker, visited=None):
        """
        Recursively gets historical data series for a ticker.
        If derived, evaluates formula over common dates of underlying series.
        If not derived, calls get_historical_series.
        Handles circular references.
        Returns dict {datetime.date: value} or raises error.
        """
        if visited is None:
            visited = set()
        if ticker in visited:
            logger.error(f"Circular reference detected in historical evaluation involving: {ticker} in chain {visited}")
            raise ValueError(f"Circular reference detected in historical data for: {ticker}")
        visited.add(ticker)

        logger.debug(f"Getting historical data for: {ticker} (Visited: {visited})")

        session = Session()
        try:
            derived = session.query(DerivedTicker).filter_by(ticker=ticker).first()

            if derived:
                logger.debug(f"'{ticker}' is derived (historical). Formula: {derived.formula}")
                underlying_tickers = extract_tickers(derived.formula)
                historical_series_map = {} # Store { ticker: {date: value} }

                for ut in underlying_tickers:
                    try:
                        # Recursively call get_historical_data
                        series = DerivedDataSource.get_historical_data(ut, visited.copy())
                        if not series:
                             # If underlying data is missing, we cannot calculate derived series
                             logger.warning(f"Historical data for underlying ticker '{ut}' not found (needed by '{ticker}').")
                             raise ValueError(f"Missing historical data for underlying ticker: {ut}")
                        historical_series_map[ut] = series
                    except ValueError as e:
                         logger.error(f"Error getting historical data for underlying ticker '{ut}': {e}")
                         raise ValueError(f"Failed to get historical data for underlying '{ut}': {str(e)}")

                # Find common dates across all underlying series
                if not historical_series_map: # Should not happen if underlying_tickers is not empty
                     logger.warning(f"No underlying historical series found for derived ticker '{ticker}'.")
                     return {}

                try:
                     common_dates = set.intersection(*(set(data.keys()) for data in historical_series_map.values()))
                except Exception as date_err:
                     logger.error(f"Error finding common dates for {ticker}: {date_err}")
                     return {} # Return empty if date intersection fails

                if not common_dates:
                     logger.warning(f"No common dates found for underlying tickers of '{ticker}'.")
                     return {}

                sorted_common_dates = sorted(list(common_dates))
                logger.debug(f"Found {len(sorted_common_dates)} common dates for '{ticker}'.")

                derived_series = {}
                for d in sorted_common_dates:
                    context_day = {}
                    valid_day = True
                    for ut in underlying_tickers:
                         value = historical_series_map[ut].get(d)
                         if value is None: # Should not happen if date is common, but check anyway
                              valid_day = False
                              logger.warning(f"Missing value for {ut} on common date {d} for {ticker}")
                              break
                         context_day[ut] = value

                    if valid_day:
                        try:
                            # Evaluate formula for this day's context
                            derived_value = safe_eval_expr(derived.formula, context_day)
                            derived_series[d] = derived_value
                        except (ValueError, TypeError) as eval_err:
                            # Log error but continue if possible, inserting None for this date
                            logger.debug(f"Daily evaluation error for '{ticker}' on {d}: {eval_err}. Context: {context_day}")
                            derived_series[d] = None # Mark as None if eval fails for a day
                    else:
                         derived_series[d] = None


                logger.debug(f"Finished calculating historical derived series for '{ticker}'.")
                return derived_series

            else:
                # Not a derived ticker – fall back to the base historical lookup
                logger.debug(f"'{ticker}' is not derived. Looking up base historical series.")
                 # Ensure the base ticker actually exists in AssetQuote before fetching
                quote_exists = session.query(AssetQuote.ticker).filter_by(ticker=ticker).first()
                if not quote_exists:
                     logger.warning(f"Ticker '{ticker}' not found in DerivedTickers or AssetQuotes (historical).")
                     return {} # Return empty dict if base ticker doesn't exist

                session.close() # Close before calling util function
                return get_historical_series(ticker) # Returns {date: value} or {}

        finally:
            if session.is_active:
                session.close()
            if ticker in visited:
                 visited.remove(ticker)