import datetime
import time
import pandas as pd
from decimal import Decimal, InvalidOperation # Added InvalidOperation
from collections import Counter
import os
import logging
import csv
import re
import ast
import operator as op
from models import Asset, Session, AssetQuote, AssetOHLCV, CurrencyAsset, CryptoAsset # Added CurrencyAsset, CryptoAsset
from sqlalchemy.orm import joinedload # For potential eager loading if needed

logger = logging.getLogger(__name__)

# --- Safe Conversion ---
def safe_convert(value, convert_func, default=None):
    """Converts value using convert_func, returning default on error or if value is None/NaN."""
    if value is None or (isinstance(value, float) and pd.isna(value)):
        return default
    try:
        return convert_func(value)
    except (ValueError, TypeError, InvalidOperation) as e: # Catch Decimal errors too
        # Optionally log the conversion error
        # logger.debug(f"Safe convert failed for value '{value}' with {convert_func.__name__}: {e}")
        return default

# --- List Chunking ---
def chunk_list(lst, chunk_size):
    """Yield successive chunk_size chunks from lst."""
    if chunk_size <= 0:
        yield lst
        return
    for i in range(0, len(lst), chunk_size):
        yield lst[i:i + chunk_size]

# --- Global query counter and persistence functions ---
query_counter = Counter()
last_saved_counts = {} # Store the state at last save to calculate delta

def load_query_counter():
    """Loads query counts from the database into the in-memory Counter."""
    global query_counter, last_saved_counts
    logger.info("Loading query counter from database...")
    session = Session()
    try:
        from models import QueryCount # Import here to avoid circular dependency issues at module level
        query_counts = session.query(QueryCount).all()
        loaded_count = 0
        for qc in query_counts:
            key = (qc.ticker, qc.asset_type)
            query_counter[key] = qc.count
            last_saved_counts[key] = qc.count # Initialize last saved state
            loaded_count += 1
        logger.info(f"Loaded {loaded_count} query count records.")
    except Exception as e:
        logger.error(f"Error loading query counter: {e}", exc_info=True)
        # Decide how to handle: raise error, or start with empty counter? Start empty.
        query_counter = Counter()
        last_saved_counts = {}
    finally:
        session.close()

def save_query_counter():
    """Saves changes (delta) in the in-memory query counter to the database."""
    global query_counter, last_saved_counts
    logger.debug("Saving query counter changes to database...")
    session = Session()
    saved_count = 0
    try:
        from models import QueryCount # Import here

        current_items = list(query_counter.items()) # Create a copy to iterate over

        for key, current_count in current_items:
            ticker, asset_type = key
            baseline = last_saved_counts.get(key, 0)
            delta = current_count - baseline

            if delta != 0: # Only save if there's a change or it's a new key
                # Try to update existing record first
                updated = session.query(QueryCount).filter_by(ticker=ticker, asset_type=asset_type).update(
                    {QueryCount.count: QueryCount.count + delta}, # Atomic increment/decrement if possible
                    synchronize_session=False # Important for bulk operations or when not loading object first
                )

                if not updated: # If no record was updated, it's likely new
                     # Verify it doesn't exist before inserting to avoid race conditions (less likely here)
                     exists = session.query(QueryCount.ticker).filter_by(ticker=ticker, asset_type=asset_type).first()
                     if not exists:
                         try:
                              session.add(QueryCount(ticker=ticker, asset_type=asset_type, count=current_count))
                              logger.debug(f"Added new query count for {key}: {current_count}")
                         except Exception as insert_err:
                              logger.error(f"Error adding new query count for {key}: {insert_err}")
                              session.rollback() # Rollback specific insert attempt
                              continue # Skip this key
                     else:
                          # This case means update failed unexpectedly, log it. Maybe retry update?
                          logger.warning(f"Update failed for existing key {key}, but it exists. Count mismatch? Baseline: {baseline}, Current: {current_count}")
                          # Force set the value as fallback
                          session.query(QueryCount).filter_by(ticker=ticker, asset_type=asset_type).update(
                               {QueryCount.count: current_count}, synchronize_session=False
                          )

                last_saved_counts[key] = current_count # Update baseline for next save
                saved_count += 1

        session.commit()
        logger.info(f"Saved changes for {saved_count} query count keys.")

    except Exception as e:
        session.rollback()
        logger.error(f"Error saving query counter: {e}", exc_info=True)
        # Don't raise, as this runs in a background thread
    finally:
        session.close()


# --- Currency List ---
def get_currency_list():
    """Reads currency codes and names from a CSV file."""
    logger.debug("Attempting to load currency list...") # Log start
    currency_list = []
    # Ensure path is relative to the script location or use absolute path
    script_dir = os.path.dirname(os.path.abspath(__file__))
    file_path = os.path.join(script_dir, "data", "physical_currency_list.csv") # Go up one level from utils
    logger.debug(f"Calculated currency list file path: {file_path}") # Log calculated path

    if os.path.exists(file_path):
        logger.debug(f"File found at: {file_path}") # Log file found
        try:
            with open(file_path, mode='r', newline='', encoding='utf-8') as csvfile:
                logger.debug("Successfully opened file. Reading headers...") # Log file opened
                # Detect header names automatically
                reader = csv.DictReader(csvfile)

                # Log the exact fieldnames read by DictReader
                if reader.fieldnames:
                     logger.debug(f"CSV DictReader fieldnames: {reader.fieldnames}")
                else:
                     logger.warning("CSV DictReader could not detect fieldnames (empty file or header issue?).")
                     return [] # Return empty if no fieldnames

                # Try different common header names
                code_headers = ["currency code", "Currency Code", "code"]
                name_headers = ["currency name", "Currency Name", "name"]

                actual_code_header = next((h for h in code_headers if h in reader.fieldnames), None)
                actual_name_header = next((h for h in name_headers if h in reader.fieldnames), None)

                # Log detected headers
                logger.debug(f"Detected headers: Code='{actual_code_header}', Name='{actual_name_header}'")

                if not actual_code_header or not actual_name_header:
                    # Use ERROR level as this prevents loading
                    logger.error(f"Could not find required headers ({code_headers} / {name_headers}) in {file_path}. Fieldnames found: {reader.fieldnames}")
                    return [] # Return empty list

                logger.debug("Processing CSV rows...") # Log start of row processing
                row_count = 0
                for row in reader:
                    row_count += 1
                    # Log the first few rows for inspection
                    if row_count <= 3:
                         logger.debug(f"Processing row {row_count} data (raw): {row}")

                    code = row.get(actual_code_header, "").strip().upper()
                    name = row.get(actual_name_header, "").strip()
                    if code and name:
                        currency_list.append((code, name))
                    else:
                        # Log if a row is skipped due to missing code or name
                        logger.debug(f"Skipping row {row_count} due to missing code/name. Code='{code}', Name='{name}'")

                logger.debug(f"Finished processing {row_count} rows. Found {len(currency_list)} valid currency pairs.") # Log completion

        except Exception as e:
            # Log the exception with traceback
            logger.error(f"Error reading currency list file {file_path}: {e}", exc_info=True)
            return [] # Return empty list on error
    else:
        # Use WARNING level as the file is expected to exist
        logger.warning(f"Currency list file not found at {file_path}. Cannot load currencies.")
        # Return empty list implicitly here, but explicit is clearer
        return []

    # Log the final result before returning
    logger.info(f"Returning currency list with {len(currency_list)} items.")
    return currency_list

# --- Database Prepopulation ---
def prepopulate_currency_assets():
    """Ensures essential currency assets (like USD, USDT) exist in the database."""
    logger.info("Prepopulating essential currency/crypto assets...")
    currency_list = get_currency_list()
    session = Session()
    try:
        # Ensure base currencies from list exist
        added_count = 0
        for currency_code, currency_name in currency_list:
            exists = session.query(CurrencyAsset.symbol).filter_by(symbol=currency_code).first()
            if not exists:
                asset_currency = CurrencyAsset(
                    asset_type="CURRENCY",
                    symbol=currency_code,
                    name=currency_name,
                    source_asset_key=currency_code # Usually the code itself for currencies
                )
                session.add(asset_currency)
                added_count += 1
                logger.debug(f"Added CurrencyAsset: {currency_code}")

        # Ensure USDT exists (treated as a CURRENCY for quoting crypto)
        usdt_exists = session.query(Asset.symbol).filter(Asset.asset_type=="CURRENCY", Asset.symbol=="USDT").first()
        if not usdt_exists:
             asset_usdt_quote = CurrencyAsset(asset_type="CURRENCY", symbol="USDT", name="Tether USD", source_asset_key="USDT")
             session.add(asset_usdt_quote)
             added_count += 1
             logger.debug("Added CurrencyAsset: USDT")

        # Ensure USD exists explicitly (might be in list, but double-check)
        usd_exists = session.query(CurrencyAsset.symbol).filter_by(symbol="USD").first()
        if not usd_exists:
            asset_usd = CurrencyAsset(asset_type="CURRENCY", symbol="USD", name="US Dollar", source_asset_key="USD")
            session.add(asset_usd)
            added_count += 1
            logger.debug("Added CurrencyAsset: USD")


        if added_count > 0:
            session.commit()
            logger.info(f"Prepopulated {added_count} missing essential assets.")
        else:
             logger.info("Essential assets already exist.")

    except Exception as e:
        session.rollback()
        logger.error(f"Error prepopulating currency assets: {e}", exc_info=True)
        # Don't raise, allow app to continue if possible
    finally:
        session.close()


# --- Derived Ticker Utility Functions ---

# Safe evaluation of arithmetic expressions using AST
allowed_operators = {
    ast.Add: op.add,    # +
    ast.Sub: op.sub,    # -
    ast.Mult: op.mul,   # *
    ast.Div: op.truediv,# /
    ast.Pow: op.pow,    # ** (Added)
    ast.USub: op.neg    # - (unary)
}

# Consider allowing basic math functions safely
allowed_funcs = {
     'abs': abs,
     'round': round,
     # Add more safe functions like 'min', 'max' if needed
     # Be VERY careful about exposing functions that could interact with the system (like eval, exec, open, etc.)
}

def safe_eval_expr(expr, context):
    """
    Safely evaluate an arithmetic expression with given context.
    Allows basic arithmetic, exponentiation, specified functions (abs, round),
    variables from context, and numeric constants.
    Handles attribute access for tickers like 'BTC.USD'.
    """
    try:
        node = ast.parse(expr, mode='eval')
    except SyntaxError as syn_err:
        raise ValueError(f"Invalid formula syntax: {syn_err}")

    # Helper to reconstruct full ticker names like 'BTC.USD' from AST nodes
    def get_full_name(n):
        if isinstance(n, ast.Name):
            return n.id
        elif isinstance(n, ast.Attribute):
             base = get_full_name(n.value)
             return f"{base}.{n.attr}"
             # For deeper nesting like a.b.c, this would need recursion,
             # but for tickers like 'X.Y', this is sufficient.
        else:
            raise TypeError(f"Unsupported node type for ticker name: {type(n)}")

    def eval_node(n):
        if isinstance(n, ast.Expression):
            return eval_node(n.body)
        elif isinstance(n, ast.Num):  # Legacy Python < 3.8
            return n.n
        elif isinstance(n, ast.Constant): # Python 3.8+
            # Ensure only numeric constants are allowed
            if isinstance(n.value, (int, float)):
                return n.value
            else:
                raise ValueError(f"Unsupported constant type: {type(n.value)}")
        elif isinstance(n, ast.BinOp):
            left = eval_node(n.left)
            right = eval_node(n.right)
            op_func = allowed_operators.get(type(n.op))
            if op_func is None:
                raise TypeError(f"Unsupported binary operator: {type(n.op)}")
            # Add checks for division by zero?
            if isinstance(n.op, ast.Div) and right == 0:
                 raise ValueError("Division by zero")
            return op_func(left, right)
        elif isinstance(n, ast.UnaryOp):
            operand = eval_node(n.operand)
            op_func = allowed_operators.get(type(n.op))
            if op_func is None:
                raise TypeError(f"Unsupported unary operator: {type(n.op)}")
            return op_func(operand)
        elif isinstance(n, (ast.Name, ast.Attribute)):
             # Handle simple names (AAPL) and dotted names (BTC.USD)
             full_name = get_full_name(n)
             if full_name in context:
                 # Ensure value from context is numeric before using
                 value = context[full_name]
                 if not isinstance(value, (int, float)):
                      raise ValueError(f"Value for ticker '{full_name}' is not numeric: {value}")
                 return value
             else:
                 raise ValueError(f"Unknown ticker or variable: '{full_name}'")
        elif isinstance(n, ast.Call):
             func_name = n.func.id if isinstance(n.func, ast.Name) else None
             if func_name in allowed_funcs:
                  args = [eval_node(arg) for arg in n.args]
                  # Add basic type checking for function args if necessary
                  return allowed_funcs[func_name](*args)
             else:
                  raise TypeError(f"Unsupported function call: {func_name}")

        else:
            raise TypeError(f"Unsupported expression type: {type(n)}")

    try:
        result = eval_node(node)
        if not isinstance(result, (int, float)):
             raise ValueError(f"Evaluation resulted in non-numeric type: {type(result)}")
        return result
    except KeyError as ke:
         raise ValueError(f"Missing value for ticker in context: {ke}")
    # Other exceptions (TypeError, ValueError) will propagate


def extract_tickers(formula):
    """
    Extract potential ticker symbols (uppercase letters, digits, dots, underscores, hyphens)
    from a formula string, ignoring numbers and basic operators.
    """
    # Improved regex: Handles A-Z, 0-9, ., _, -
    # It looks for sequences starting with a letter or digit, potentially containing the allowed chars.
    potential_tickers = re.findall(r"[A-Z0-9][A-Z0-9._-]*", formula)

    # Filter out pure numbers and common keywords/operators if needed
    excluded = set(['abs', 'round']) # Add any other function names used
    tickers = []
    for token in potential_tickers:
        if token in excluded:
             continue
        try:
            # Try converting to float, if successful, it's a number, not a ticker
            float(token)
        except ValueError:
            # If conversion fails, it's likely a ticker symbol
            tickers.append(token)

    return list(set(tickers)) # Return unique tickers


def get_historical_series(ticker):
    """
    Retrieve historical close price series for a given *non-derived* ticker from AssetOHLCV.
    Returns a dict mapping date (datetime.date) to close price (float).
    """
    logger.debug(f"Fetching historical series for base ticker: {ticker}")
    session = Session()
    series = {}
    try:
        # Find the AssetQuote corresponding to the ticker
        asset_quote = session.query(AssetQuote).filter_by(ticker=ticker).first()
        if asset_quote:
            # Fetch OHLCV records, ordered by date
            records = session.query(AssetOHLCV).filter_by(
                asset_quote_id=asset_quote.id
            ).order_by(AssetOHLCV.price_date).all()

            # Convert to dict {date: close_price}
            for record in records:
                if record.price_date and record.close_price is not None:
                    # Use date part only as key
                    price_date_obj = record.price_date.date()
                    # Convert Decimal close price to float
                    series[price_date_obj] = safe_convert(record.close_price, float)
            logger.debug(f"Found {len(series)} historical points for {ticker}")
        else:
             logger.warning(f"No AssetQuote found for ticker '{ticker}' when fetching historical series.")

    except Exception as e:
        logger.error(f"Error fetching historical series for {ticker}: {e}", exc_info=True)
        # Return empty dict on error
        series = {}
    finally:
        session.close()
    return series


def get_latest_price_for_asset(ticker):
    """
    Retrieve the latest price for a given *non-derived* ticker by looking up AssetQuote
    and calling the appropriate DataSource method. Returns price or "NOT_FOUND".
    """
    logger.debug(f"Fetching latest price for base asset: {ticker}")
    session = Session()
    try:
        from data_fetchers import StockDataSource, CryptoDataSource, CurrencyDataSource # Import locally

        asset_quote = session.query(AssetQuote).options(
             joinedload(AssetQuote.data_source) # Eager load data source if needed often
        ).filter_by(ticker=ticker).first()

        if asset_quote and asset_quote.source_ticker:
            asset_type = asset_quote.from_asset_type.upper() if asset_quote.from_asset_type else None
            source_ticker = asset_quote.source_ticker
            data_source_name = asset_quote.data_source.name if asset_quote.data_source else "Unknown"
            logger.debug(f"Found AssetQuote for {ticker}: Type={asset_type}, SourceTicker={source_ticker}, DataSource={data_source_name}")

            result = None
            if asset_type == "STOCK":
                result = StockDataSource.get_latest_price(source_ticker)
            elif asset_type == "CRYPTO":
                result = CryptoDataSource.get_latest_price(source_ticker)
            elif asset_type == "CURRENCY":
                result = CurrencyDataSource.get_latest_price(source_ticker)
            else:
                logger.warning(f"Unsupported asset type '{asset_type}' for ticker '{ticker}'")
                result = "NOT_FOUND" # Treat unsupported as not found

            # Ensure result is price or "NOT_FOUND"
            if result is None: # If DataSource method had an error
                 logger.error(f"DataSource returned None for {ticker} ({source_ticker})")
                 return "NOT_FOUND" # Treat internal errors as not found for simplicity
            return result # Should be price (float/int) or "NOT_FOUND" string

        else:
            logger.warning(f"No AssetQuote or source_ticker found for ticker '{ticker}'")
            return "NOT_FOUND"

    except Exception as e:
        logger.error(f"Error fetching latest price for base asset {ticker}: {e}", exc_info=True)
        return "NOT_FOUND" # Return consistent "NOT_FOUND" on error
    finally:
        session.close()