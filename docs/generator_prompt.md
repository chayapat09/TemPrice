### Generating Stock Data Model
```
from `datasource/yfinance.md` please design a data model to store stock quote and stock price but in quote please union column from th and us output and extract only cols that is static data (rarely change) of given stock/quote.
```
### Design Service
```
please design a price provider service such that a. it has historical data from 2020-1-1 b. it has latest daily update data as soon as possible but also considered c. it has api to fetch latest data query by symbol(ticker) but our service will pull from data source only once every 5 min to avoid rate limit. d. given asset type we provided api to list all ticker and metadata e. it has api to list historical data for given ticker and also calculated number about frequently that we can fetch to polulated historical data also latest data carefully , please refer and use above code example in top most section for code to fetch data from data source (yfinance)

Design Recommendation 
1. We has two Jobs a. Full Sync (for populated all required historical data and Quote) b. Delta ( for populated Daily updated data with date range to be past two days and data was updated to database also update Quote) with persistance counter store on database where we left for delta jobs which run daily , Full Sync is run once but when run all data will be sync with source until latest data we get
2. Historical Data and Quote Data were fetch from database to serve our API
3. Latest Data we fetch in to memory cache and our api serve from that cache
```

10. From what i know that running to fetch a big range of date data take a long time thus i want my service to always being up to date please design a price service such that a. it has historical data from 2020-1-1 b. it has latest daily update data as soon as possible but also considered c. it has api to fetch latest data query by symbol and asset type `STOCK` , `CRYPTO` , `CURRENCY`... but our service will pull from data source only once every 5 min to avoid rate limit. d. given asset type we provided api to list all asset and metadata





11. Redesign database such that Asset It self (bitcoin, Tesla , THB ....) has different data entity from Quote (Which is price between two thing ex. Tesla / USD = TSLA Quote , BTC / USDT = BitcoinUSD Quote) so in future