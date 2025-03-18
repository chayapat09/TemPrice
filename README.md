# Tem Capital

## Project Setup Instructions

Follow these instructions to set up and run the Tem Capital application locally.

---

### 1. Clone the Repository

Clone the Tem Capital repository and navigate to the project directory:

```bash
git clone <repository-url>
cd TemCapital
```

---

### 2. Create and Activate a Virtual Environment

**On UNIX/Linux/MacOS:**

```bash
python3 -m venv venv
source venv/bin/activate
```

**On Windows:**

```cmd
python -m venv venv
venv\Scripts\activate
```

---

### 3. Install Dependencies

Install the required Python dependencies:

```bash
pip install -r requirements.txt
```

---

### 4. Run the Application

Start the application using:

```bash
python app.py
```

The app will be available at:

```
http://127.0.0.1:8080
```

---

### Optional: Running via Provided Scripts

- **UNIX-like Systems:**

```bash
./run.sh
```

- **Windows:**

Double-click `run.bat` or execute it from the command prompt:

```cmd
run.bat
```

---

## Project Structure

```
investment_tracker/
├── app.py
└── templates/
    ├── base.html
    ├── dashboard.html
    ├── transaction.html
    ├── cash.html
    ├── edit_position.html
    └── summary.html
```

---

## Pending Features (TODO)

- **Real-Time Price Feed:** Implement a Python-based price feed that supports subscribing multiple symbols.
- **Historical Price Data:** Integrate mandatory historical price data.
- **Quarterly Financial Statements:** Generate quarterly statements from provided financial data.
- **Mobile Support:** Enhance UI/UX to support mobile devices.

---

## Exchange Codes Reference

- **ASE:** NYSE American (small-cap companies)
- **BTS:** Bats Global Markets (U.S. stock exchange)
- **CXI:** Not commonly associated (possible internal ticker)
- **NCM:** NASDAQ Capital Market (small-cap companies)
- **NGM:** NASDAQ Global Market (mid-cap companies)
- **NMS:** NASDAQ Global Select Market (large-cap companies)
- **NYQ:** New York Stock Exchange (NYSE)
- **OEM:** OTC Markets Expert Market (OTC segment)
- **OQB:** OTCQB Venture Market (early-stage companies)
- **OQX:** OTCQX (top-tier OTC market)
- **PCX:** NYSE Arca (stocks and options trading)
- **PNK:** OTC Pink Sheets (highly speculative OTC market)
- **YHD:** NASDAQ OMX Tallinn (primary Estonian exchange)

---

### Reference

For more information:
- [yfinance EquityQuery Documentation](https://yfinance-python.org/reference/api/yfinance.EquityQuery.html)




