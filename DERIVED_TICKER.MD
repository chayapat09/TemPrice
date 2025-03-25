Below is a detailed documentation covering derived tickers. It explains what a derived ticker is, how you can add, list, update, and delete them via the API, and provides guidance on constructing valid derived ticker formulas including the permitted base tickers.

---

# Derived Ticker Documentation

Derived tickers are a special type of asset within the application whose values are computed dynamically by evaluating an arithmetic formula that combines the latest prices of one or more underlying (base) tickers. These base tickers can represent stocks, cryptocurrencies, currencies, or even other derived tickers. The computed (derived) value is obtained by safely evaluating the given formula at runtime.

## 1. What Is a Derived Ticker?

- **Definition:**  
  A derived ticker is an asset whose price is not fetched directly from an external data source but is computed using an arithmetic expression (formula) that references one or more base tickers.
  
- **Purpose:**  
  They allow users to create custom indicators or combined price metrics. For example, a derived ticker could represent the sum or difference of two stock prices (e.g., `"AAPL + MSFT"`) or a weighted combination of prices.

- **Computation Process:**  
  When a derived ticker is requested:
  - The system extracts the underlying ticker symbols from the formula.
  - For each underlying ticker, the system attempts to fetch the latest price:
    - If the base ticker is also a derived ticker, its formula is evaluated recursively.
    - If the base ticker is a direct asset (e.g., a stock fetched via Yahoo Finance, a crypto from Binance, or a currency from AlphaVantage), its latest price is retrieved from the appropriate data source.
  - The arithmetic expression is then safely evaluated using only basic operations (addition, subtraction, multiplication, division, and negation) via a controlled expression evaluator.

- **Circular Reference Handling:**  
  The system is designed to detect and prevent circular references (for example, if ticker A’s formula depends on ticker B and vice versa) and will return an error in such cases.

---

## 2. API Endpoints for Derived Tickers

The following endpoints allow you to manage derived tickers:

### a. List Derived Tickers

- **Endpoint:**  
  `GET /api/derived`

- **Purpose:**  
  Retrieve a list of all defined derived tickers along with their formulas.

- **Response Example:**
  ```json
  [
    {
      "ticker": "DERIVED1",
      "formula": "AAPL + MSFT"
    },
    {
      "ticker": "MYINDEX",
      "formula": "GOOGL * 0.5 + AMZN * 0.5"
    }
  ]
  ```

### b. Add (Create) a New Derived Ticker

- **Endpoint:**  
  `POST /api/derived`

- **Purpose:**  
  Create a new derived ticker by specifying a unique ticker identifier and a formula.

- **Request Body (JSON):**
  ```json
  {
    "ticker": "DERIVED1",
    "formula": "AAPL + MSFT"
  }
  ```
  
  - **`ticker` (string, required):**  
    A unique identifier for the derived ticker. This identifier is used to reference the derived asset.
  
  - **`formula` (string, required):**  
    An arithmetic expression that combines one or more base tickers. For example, `"AAPL + MSFT"`.  
    **Important:**  
    - The formula should use only basic arithmetic operators: `+`, `-`, `*`, `/`, and can include unary negation.  
    - The allowed variables (base tickers) are expected to be in uppercase alphanumeric format.  
    - Base tickers can be any valid asset ticker that the system can fetch a latest price for (stocks, cryptocurrencies, currencies) or other previously created derived tickers.

- **Response Example:**
  ```json
  {
    "message": "Derived ticker DERIVED1 created successfully."
  }
  ```

- **Error Responses:**
  - Missing `ticker` or `formula`:
    ```json
    { "error": "Ticker and formula are required" }
    ```
  - If a derived ticker with the given identifier already exists:
    ```json
    { "error": "Derived ticker with this ticker already exists" }
    ```

### c. Update an Existing Derived Ticker

- **Endpoint:**  
  `PUT /api/derived/<ticker>`

- **Purpose:**  
  Update the formula of an existing derived ticker.

- **Path Parameter:**  
  - `<ticker>`: The unique identifier of the derived ticker you wish to update.

- **Request Body (JSON):**
  ```json
  {
    "formula": "AAPL * 0.6 + MSFT * 0.4"
  }
  ```

- **Response Example:**
  ```json
  {
    "message": "Derived ticker DERIVED1 updated successfully."
  }
  ```

- **Error Responses:**
  - Missing `formula` in the request body:
    ```json
    { "error": "Formula is required" }
    ```
  - If the specified derived ticker does not exist:
    ```json
    { "error": "Derived ticker not found" }
    ```

### d. Delete a Derived Ticker

- **Endpoint:**  
  `DELETE /api/derived/<ticker>`

- **Purpose:**  
  Remove a derived ticker from the system.

- **Path Parameter:**  
  - `<ticker>`: The unique identifier of the derived ticker to be deleted.

- **Response Example:**
  ```json
  {
    "message": "Derived ticker DERIVED1 deleted successfully."
  }
  ```

- **Error Responses:**
  - If the derived ticker is not found:
    ```json
    { "error": "Derived ticker not found" }
    ```

---

## 3. Constructing New Derived Tickers

When constructing a new derived ticker, keep the following guidelines in mind:

### a. Formula Syntax and Operators

- **Allowed Operators:**  
  Only basic arithmetic operations are allowed:
  - Addition: `+`
  - Subtraction: `-`
  - Multiplication: `*`
  - Division: `/`
  - Unary negation: `-` (applied to a number or a variable)

- **Example Formulas:**
  - **Simple Addition:** `"AAPL + MSFT"`  
    Computes the sum of the latest prices for AAPL and MSFT.
  
  - **Weighted Average:** `"AAPL * 0.5 + MSFT * 0.5"`  
    Computes the average of AAPL and MSFT prices.
  
  - **Difference:** `"GOOGL - FB"`  
    Computes the difference between Google’s and Facebook’s latest prices.

### b. Base Ticker Values

- **Permitted Base Tickers:**
  - **Direct Asset Tickers:**  
    Any ticker that exists as an asset in the system (stocks, crypto, or currency). For instance:
    - Stocks: `"AAPL"`, `"TSLA"`, `"GOOGL"`, etc.
    - Cryptocurrencies: `"BTC"`, `"ETH"`, etc.
    - Currencies: `"EUR"`, `"JPY"`, etc. (with the understanding that non-USD currencies are converted using the currency exchange rates).
  
  - **Other Derived Tickers:**  
    You can also reference an already created derived ticker as long as it does not lead to circular dependencies. For example, if you have a derived ticker `"TECHINDEX"` defined as `"AAPL + MSFT"`, you could create another derived ticker like `"DOUBLE_TECH"` with the formula `"TECHINDEX * 2"`.
  
- **Variable Naming and Format:**
  - The system extracts ticker symbols using a regular expression that matches sequences of uppercase letters and digits.  
  - Ensure that the base tickers in your formula exactly match the identifiers of existing assets or derived tickers. For instance, if the asset is registered as `"AAPL"`, do not use `"aapl"` or `"Aapl"`.

### c. Tips for Constructing Formulas

- **Clarity:**  
  Write clear formulas that are easy to read and maintain. If combining several tickers, consider using parentheses for clarity, for example:  
  `" (AAPL + MSFT) / 2 "`
  
- **Avoid Complex Nesting:**  
  While you can build derived tickers on top of other derived tickers, be cautious not to create overly complex or nested formulas that are hard to troubleshoot.

- **Testing:**  
  Before using the formula in production, you may want to verify that each base ticker in your formula returns a valid price. If any base ticker returns `NOT_FOUND` or an error, the derived ticker computation will fail.

- **No Arbitrary Code:**  
  The evaluation is performed using a safe arithmetic evaluator that only permits the allowed operators and variable names. Do not expect functions or advanced Python expressions to work.

---

## Summary

- **Derived Ticker Concept:**  
  Derived tickers let you define custom assets whose values are computed using a formula that references one or more base tickers.
  
- **Managing Derived Tickers via API:**  
  Use the provided endpoints to list, create, update, and delete derived tickers.
  
- **Constructing Valid Formulas:**  
  - Use only basic arithmetic operators.  
  - Ensure that each ticker in the formula is a valid base ticker (stock, crypto, currency, or an existing derived ticker).  
  - Avoid circular references to ensure successful evaluation.

By following these guidelines, you can leverage derived tickers to build custom metrics and indicators that suit your financial analysis needs.