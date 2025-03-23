Foreign Exchange Rates (FX)
APIs under this section provide a wide range of data feed for realtime and historical forex (FX) rates.


CURRENCY_EXCHANGE_RATE Trending

This API returns the realtime exchange rate for a pair of digital currency (e.g., Bitcoin) and physical currency (e.g., USD).


API Parameters
❚ Required: function

The function of your choice. In this case, function=CURRENCY_EXCHANGE_RATE

❚ Required: from_currency

The currency you would like to get the exchange rate for. It can either be a physical currency or digital/crypto currency. For example: from_currency=USD or from_currency=BTC.

❚ Required: to_currency

The destination currency for the exchange rate. It can either be a physical currency or digital/crypto currency. For example: to_currency=USD or to_currency=BTC.

❚ Required: apikey

Your API key. Claim your free API key here.


Examples (click for JSON output)
US Dollar to Japanese Yen:
https://www.alphavantage.co/query?function=CURRENCY_EXCHANGE_RATE&from_currency=USD&to_currency=JPY&apikey=demo

Bitcoin to Euro:
https://www.alphavantage.co/query?function=CURRENCY_EXCHANGE_RATE&from_currency=BTC&to_currency=EUR&apikey=demo


Language-specific guides
Python NodeJS PHP C#/.NET Other
import requests

# replace the "demo" apikey below with your own key from https://www.alphavantage.co/support/#api-key
url = 'https://www.alphavantage.co/query?function=CURRENCY_EXCHANGE_RATE&from_currency=USD&to_currency=JPY&apikey=demo'
r = requests.get(url)
data = r.json()

print(data)

Reponse 
{
    "Realtime Currency Exchange Rate": {
        "1. From_Currency Code": "USD",
        "2. From_Currency Name": "United States Dollar",
        "3. To_Currency Code": "THB",
        "4. To_Currency Name": "Thai Baht",
        "5. Exchange Rate": "33.83500000",
        "6. Last Refreshed": "2025-03-21 11:42:10",
        "7. Time Zone": "UTC",
        "8. Bid Price": "33.83420000",
        "9. Ask Price": "33.83650000"
    }
}


Language-specific guides
Python NodeJS PHP C#/.NET Other
import requests

# replace the "demo" apikey below with your own key from https://www.alphavantage.co/support/#api-key
url = 'https://www.alphavantage.co/query?function=FX_INTRADAY&from_symbol=EUR&to_symbol=USD&interval=5min&apikey=demo'
r = requests.get(url)
data = r.json()

print(data)

FX_DAILY

This API returns the daily time series (timestamp, open, high, low, close) of the FX currency pair specified, updated realtime.


API Parameters
❚ Required: function

The time series of your choice. In this case, function=FX_DAILY

❚ Required: from_symbol

A three-letter symbol from the forex currency list. For example: from_symbol=EUR

❚ Required: to_symbol

A three-letter symbol from the forex currency list. For example: to_symbol=USD

❚ Optional: outputsize

By default, outputsize=compact. Strings compact and full are accepted with the following specifications: compact returns only the latest 100 data points in the daily time series; full returns the full-length daily time series. The "compact" option is recommended if you would like to reduce the data size of each API call.

❚ Optional: datatype

By default, datatype=json. Strings json and csv are accepted with the following specifications: json returns the daily time series in JSON format; csv returns the time series as a CSV (comma separated value) file.

❚ Required: apikey

Your API key. Claim your free API key here.


Examples (click for JSON output)
https://www.alphavantage.co/query?function=FX_DAILY&from_symbol=EUR&to_symbol=USD&apikey=demo

https://www.alphavantage.co/query?function=FX_DAILY&from_symbol=EUR&to_symbol=USD&outputsize=full&apikey=demo

Downloadable CSV file:
https://www.alphavantage.co/query?function=FX_DAILY&from_symbol=EUR&to_symbol=USD&apikey=demo&datatype=csv


Language-specific guides
Python NodeJS PHP C#/.NET Other
import requests

# replace the "demo" apikey below with your own key from https://www.alphavantage.co/support/#api-key
url = 'https://www.alphavantage.co/query?function=FX_DAILY&from_symbol=EUR&to_symbol=USD&apikey=demo'
r = requests.get(url)
data = r.json()

print(data)

Response 
```
{
    "Meta Data": {
        "1. Information": "Forex Daily Prices (open, high, low, close)",
        "2. From Symbol": "EUR",
        "3. To Symbol": "USD",
        "4. Output Size": "Full size",
        "5. Last Refreshed": "2025-03-21",
        "6. Time Zone": "UTC"
    },
    "Time Series FX (Daily)": {
        "2025-03-21": {
            "1. open": "1.08535",
            "2. high": "1.08590",
            "3. low": "1.08504",
            "4. close": "1.08520"
        },
        "2025-03-20": {
            "1. open": "1.09045",
            "2. high": "1.09173",
            "3. low": "1.08143",
            "4. close": "1.08539"
        },
        "2025-03-19": {
            "1. open": "1.09436",
            "2. high": "1.09460",
            "3. low": "1.08603",
            "4. close": "1.09033"
        },
        "2025-03-18": {
            "1. open": "1.09214",
            "2. high": "1.09547",
            "3. low": "1.08921",
            "4. close": "1.09442"
        },
        "2025-03-17": {
            "1. open": "1.08800",
            "2. high": "1.09297",
            "3. low": "1.08680",
            "4. close": "1.09212"
        },
        "2025-03-14": {
            "1. open": "1.08515",
            "2. high": "1.09127",
            "3. low": "1.08304",
            "4. close": "1.08765"
        },
        ... rest of data
    }
}
```


Currency List(CSV) https://www.alphavantage.co/physical_currency_list/ 

example data in csv
```
currency code,currency name
AED,United Arab Emirates Dirham
AFN,Afghan Afghani
ALL,Albanian Lek
AMD,Armenian Dram
ANG,Netherlands Antillean Guilder
AOA,Angolan Kwanza
ARS,Argentine Peso
AUD,Australian Dollar
AWG,Aruban Florin
AZN,Azerbaijani Manat
BAM,Bosnia-Herzegovina Convertible Mark
BBD,Barbadian Dollar
```

but we already has this file on `./data/physical_currency_list.csv` please read from that file

please add support for currency price data to this system with realtime cache price data update every 6HR , and ingest all data pair with to_symbol = USD (all currency against USD) , delta , full sync has same feature/frequency as other type of data , and for this data asset_type = 'CURRENCY'
