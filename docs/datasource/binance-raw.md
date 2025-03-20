General API Information
The following base endpoints are available. Please use whichever works best for your setup:
https://api.binance.com
https://api-gcp.binance.com
https://api1.binance.com
https://api2.binance.com
https://api3.binance.com
https://api4.binance.com
The last 4 endpoints in the point above (api1-api4) should give better performance but have less stability.
All endpoints return either a JSON object or array.
Data is returned in ascending order. Oldest first, newest last.
All time and timestamp related fields in the JSON responses are in milliseconds by default. To receive the information in microseconds, please add the header X-MBX-TIME-UNIT:MICROSECOND or X-MBX-TIME-UNIT:microsecond.
Timestamp parameters (e.g. startTime, endTime, timestamp) can be passed in milliseconds or microseconds.
For APIs that only send public market data, please use the base endpoint https://data-api.binance.vision. Please refer to Market Data Only page.


HTTP Return Codes
HTTP 4XX return codes are used for malformed requests; the issue is on the sender's side.
HTTP 403 return code is used when the WAF Limit (Web Application Firewall) has been violated.
HTTP 409 return code is used when a cancelReplace order partially succeeds. (i.e. if the cancellation of the order fails but the new order placement succeeds.)
HTTP 429 return code is used when breaking a request rate limit.
HTTP 418 return code is used when an IP has been auto-banned for continuing to send requests after receiving 429 codes.
HTTP 5XX return codes are used for internal errors; the issue is on Binance's side. It is important to NOT treat this as a failure operation; the execution status is UNKNOWN and could have been a success.


LIMITS
General Info on Limits
The following intervalLetter values for headers:
SECOND => S
MINUTE => M
HOUR => H
DAY => D
intervalNum describes the amount of the interval. For example, intervalNum 5 with intervalLetter M means "Every 5 minutes".
The /api/v3/exchangeInfo rateLimits array contains objects related to the exchange's RAW_REQUESTS, REQUEST_WEIGHT, and ORDERS rate limits. These are further defined in the ENUM definitions section under Rate limiters (rateLimitType).
Requests fail with HTTP status code 429 when you exceed the request rate limit.
IP Limits
Every request will contain X-MBX-USED-WEIGHT-(intervalNum)(intervalLetter) in the response headers which has the current used weight for the IP for all request rate limiters defined.
Each route has a weight which determines for the number of requests each endpoint counts for. Heavier endpoints and endpoints that do operations on multiple symbols will have a heavier weight.
When a 429 is received, it's your obligation as an API to back off and not spam the API.
Repeatedly violating rate limits and/or failing to back off after receiving 429s will result in an automated IP ban (HTTP status 418).
IP bans are tracked and scale in duration for repeat offenders, from 2 minutes to 3 days.
A Retry-After header is sent with a 418 or 429 responses and will give the number of seconds required to wait, in the case of a 429, to prevent a ban, or, in the case of a 418, until the ban is over.
The limits on the API are based on the IPs, not the API keys.
Unfilled Order Count
Every successful order response will contain a X-MBX-ORDER-COUNT-(intervalNum)(intervalLetter) header indicating how many orders you have placed for that interval.

To monitor this, refer to GET api/v3/rateLimit/order.
Rejected/unsuccessful orders are not guaranteed to have X-MBX-ORDER-COUNT-** headers in the response.
If you have exceeded this, you will receive a 429 error without the Retry-After header.
Please note that if your orders are consistently filled by trades, you can continuously place orders on the API. For more information, please see Spot Unfilled Order Count Rules.
The number of unfilled orders is tracked for each account.



openapi: '3.0.2'
info:
  title: Binance Public Spot API
  description: |-
    OpenAPI Specifications for the Binance Public Spot API

    API documents:
      - [https://github.com/binance/binance-spot-api-docs](https://github.com/binance/binance-spot-api-docs)
      - [https://binance-docs.github.io/apidocs/spot/en](https://binance-docs.github.io/apidocs/spot/en)
  version: '1.0'

servers:
  - url: https://api.binance.com
  - url: https://testnet.binance.vision

tags:
  - name: Market
    description: Market Data
  - name: Trade
    description: Account/Trade
  - name: Margin
    description: Margin Account/Trade
  - name: Wallet
    description: Wallet Endpoints
  - name: Sub-Account
    description: Sub-account Endpoints
  - name: Stream
    description: User Data Stream
  - name: Margin Stream
    description: Margin User Data Stream
  - name: Isolated Margin Stream
    description: Isolated User Data Stream
  - name: Savings
    description: Savings Endpoints
  - name: Mining
    description: Mining Endpoints
  - name: Futures
    description: Futures Endpoints
  - name: Futures Algo
    description: Futures Algo Endpoints
  - name: Spot Algo
    description: Spot Algo Endpoints
  - name: Portfolio Margin
    description: Portfolio Margin Endpoints
  - name: BLVT
    description: Binance Leveraged Tokens Endpoints
  - name: Fiat
    description: Fiat Endpoints
  - name: C2C
    description: Consumer-To-Consumer Endpoints
  - name: VIP Loans
    description: VIP Loans Endpoints
  - name: Crypto Loans
    description: Crypto Loans Endpoints
  - name: Pay
    description: Pay Endpoints
  - name: Convert
    description: Convert Endpoints
  - name: Rebate
    description: Rebate Endpoints
  - name: NFT
    description: NFT Endpoints
  - name: Gift Card
    description: Gift Card Endpoints
  - name: Auto-Invest
    description: Auto-Invest Endpoints
  - name: Copy Trading
    description: Copy Trading Endpoints
  - name: Simple Earn
    description: Simple Earn Endpoints
paths:
  /api/v3/ping:
    get:
      summary: Test Connectivity
      description: |-
        Test connectivity to the Rest API.

        Weight(IP): 1
      tags:
        - Market
      responses:
        '200':
          description: OK
          content:
            application/json:
              schema:
                type: object
  /api/v3/time:
    get:
      summary: Check Server Time
      description: |-
        Test connectivity to the Rest API and get the current server time.

        Weight(IP): 1
      tags:
        - Market
      responses:
        '200':
          description: Binance server UTC timestamp
          content:
            application/json:
              schema:
                type: object
                properties:
                  serverTime:
                    type: integer
                    format: int64
                    example: 1499827319559
                required:
                  - serverTime
  /api/v3/exchangeInfo:
    get:
      summary: Exchange Information
      description: |-
        Current exchange trading rules and symbol information

        - If any symbol provided in either symbol or symbols do not exist, the endpoint will throw an error.
        - All parameters are optional.
        - permissions can support single or multiple values (e.g. SPOT, ["MARGIN","LEVERAGED"])
        - If permissions parameter not provided, the default values will be ["SPOT","MARGIN","LEVERAGED"].
          - To display all permissions you need to specify them explicitly. (e.g. SPOT, MARGIN,...)

        Examples of Symbol Permissions Interpretation from the Response:
        - [["A","B"]] means you may place an order if your account has either permission "A" or permission "B".
        - [["A"],["B"]] means you can place an order if your account has permission "A" and permission "B".
        - [["A"],["B","C"]] means you can place an order if your account has permission "A" and permission "B" or permission "C". (Inclusive or is applied here, not exclusive or, so your account may have both permission "B" and permission "C".)

        Weight(IP): 10
      tags:
        - Market
      parameters:
        - $ref: '#/components/parameters/optionalSymbol'
        - $ref: '#/components/parameters/arraySymbols'
        - $ref: '#/components/parameters/permissions'
      responses:
        '200':
          description: Current exchange trading rules and symbol information
          content:
            application/json:
              schema:
                type: object
                properties:
                  timezone:
                    type: string
                    example: UTC
                  serverTime:
                    type: integer
                    format: int64
                    example: 1592882214236
                  rateLimits:
                    type: array
                    items:
                      type: object
                      properties:
                        rateLimitType:
                          type: string
                          example: "REQUEST_WEIGHT"
                        interval:
                          type: string
                          example: "MINUTE"
                        intervalNum:
                          type: integer
                          format: int32
                          example: 1
                        limit:
                          type: integer
                          format: int32
                          example: 1200
                      required:
                        - rateLimitType
                        - interval
                        - intervalNum
                        - limit
                  exchangeFilters:
                    type: array
                    items:
                      type: object
                  symbols:
                    type: array
                    items:
                      type: object
                      properties:
                        symbol:
                          type: string
                          example: "ETHBTC"
                        status:
                          type: string
                          example: "TRADING"
                        baseAsset:
                          type: string
                          example: "ETH"
                        baseAssetPrecision:
                          type: integer
                          format: int32
                          example: 8
                        quoteAsset:
                          type: string
                          example: "BTC"
                        quoteAssetPrecision:
                          type: integer
                          format: int32
                          example: 8
                        baseCommissionPrecision:
                          type: integer
                          format: int32
                          example: 8
                        quoteCommissionPrecision:
                          type: integer
                          format: int32
                          example: 8
                        orderTypes:
                          type: array
                          items:
                            type: string
                            example: "LIMIT"
                        icebergAllowed:
                          type: boolean
                          example: true
                        ocoAllowed:
                          type: boolean
                          example: true
                        otoAllowed:
                          type: boolean
                          example: false
                        quoteOrderQtyMarketAllowed:
                          type: boolean
                          example: true
                        allowTrailingStop:
                          type: boolean
                          example: false
                        cancelReplaceAllowed:
                          type: boolean
                          example: true
                        isSpotTradingAllowed:
                          type: boolean
                          example: true
                        isMarginTradingAllowed:
                          type: boolean
                          example: true
                        filters:
                          type: array
                          items:
                            type: object
                            properties:
                              filterType:
                                type: string
                                example: "PRICE_FILTER"
                              minPrice:
                                type: string
                                example: "0.00000100"
                              maxPrice:
                                type: string
                                example: "100000.00000000"
                              tickSize:
                                type: string
                                example: "0.00000100"
                            required:
                              - filterType
                              - minPrice
                              - maxPrice
                              - tickSize
                        permissions:
                          type: array
                          items:
                            type: string
                            example: "SPOT"
                        permissionSets:
                          type: array
                          items:
                            type: array
                            items:
                              type: string
                              example:
                                - "SPOT"
                                - "MARGIN"
                        defaultSelfTradePreventionMode:
                          type: string
                          example: "NONE"
                        allowedSelfTradePreventionModes:
                          type: array
                          items:
                            type: string
                            example: "NONE"
                      required:
                        - symbol
                        - status
                        - baseAsset
                        - baseAssetPrecision
                        - quoteAsset
                        - quoteAssetPrecision
                        - baseCommissionPrecision
                        - quoteCommissionPrecision
                        - orderTypes
                        - icebergAllowed
                        - ocoAllowed
                        - otoAllowed
                        - quoteOrderQtyMarketAllowed
                        - allowTrailingStop
                        - cancelReplaceAllowed
                        - isSpotTradingAllowed
                        - isMarginTradingAllowed
                        - filters
                        - permissions
                        - permissionSets
                        - defaultSelfTradePreventionMode
                        - allowedSelfTradePreventionModes
                required:
                  - timezone
                  - serverTime
                  - rateLimits
                  - exchangeFilters
                  - symbols
        '400':
          description: Bad Request
          content:
            application/json:
              schema:
                $ref: '#/components/schemas/error'
  /api/v3/depth:
    get:
      summary: Order Book
      description: |-
        | Limit               | Weight(IP)  |
        |---------------------|-------------|
        | 1-100               | 5           |
        | 101-500             | 25          |
        | 501-1000            | 50          |
        | 1001-5000           | 250         |
      tags:
        - Market
      parameters:
        - $ref: '#/components/parameters/symbol'
        - name: limit
          in: query
          description: If limit > 5000, then the response will truncate to 5000
          schema:
            type: integer
            format: int32
            default: 100
            maximum: 5000
            example: 100
      responses:
        '200':
          description: Order book
          content:
            application/json:
              schema:
                type: object
                properties:
                  lastUpdateId:
                    type: integer
                    format: int64
                  bids:
                    type: array
                    items:
                        type: array
                        items:
                          type: string
                          minItems: 2
                          maxItems: 2
                  asks:
                    type: array
                    items:
                        type: array
                        items:
                          type: string
                          minItems: 2
                          maxItems: 2
                required:
                  - lastUpdateId
                  - bids
                  - asks
              example:
                lastUpdateId: 1027024
                bids:
                -
                  - "4.00000000"
                  - "431.00000000"
                asks:
                -
                  - "4.00000200"
                  - "12.00000000"
        '400':
          description: Bad Request
          content:
            application/json:
              schema:
                $ref: '#/components/schemas/error'
  /api/v3/trades:
    get:
      summary: Recent Trades List
      description: |-
        Get recent trades.

        Weight(IP): 10
      tags:
        - Market
      parameters:
        - $ref: '#/components/parameters/symbol'
        - $ref: '#/components/parameters/limit'
      responses:
        '200':
          description: Trade list
          content:
            application/json:
              schema:
                type: array
                items:
                  $ref: '#/components/schemas/trade'
        '400':
          description: Bad Request
          content:
            application/json:
              schema:
                $ref: '#/components/schemas/error'
  /api/v3/historicalTrades:
    get:
      summary: Old Trade Lookup
      description: |-
        Get older market trades.

        Weight(IP): 10
      tags:
        - Market
      parameters:
        - $ref: '#/components/parameters/symbol'
        - $ref: '#/components/parameters/limit'
        - $ref: '#/components/parameters/fromId'
      responses:
        '200':
          description: Trade list
          content:
            application/json:
              schema:
                type: array
                items:
                  $ref: '#/components/schemas/trade'
  /api/v3/aggTrades:
    get:
      summary: Compressed/Aggregate Trades List
      description: |-
        Get compressed, aggregate trades. Trades that fill at the time, from the same order, with the same price will have the quantity aggregated.
        - If `fromId`, `startTime`, and `endTime` are not sent, the most recent aggregate trades will be returned.
        - Note that if a trade has the following values, this was a duplicate aggregate trade and marked as invalid:

          p = '0' // price

          q = '0' // qty

          f = -1 // ﬁrst_trade_id

          l = -1 // last_trade_id

        Weight(IP): 2
      tags:
        - Market
      parameters:
        - $ref: '#/components/parameters/symbol'
        - $ref: '#/components/parameters/fromId'
        - $ref: '#/components/parameters/startTime'
        - $ref: '#/components/parameters/endTime'
        - $ref: '#/components/parameters/limit'
      responses:
        '200':
          description: Trade list
          content:
            application/json:
              schema:
                type: array
                items:
                  $ref: '#/components/schemas/aggTrade'
        '400':
          description: Bad Request
          content:
            application/json:
              schema:
                $ref: '#/components/schemas/error'
  /api/v3/klines:
    get:
      summary: Kline/Candlestick Data
      description: |-
        Kline/candlestick bars for a symbol.
        Klines are uniquely identified by their open time.

        - If `startTime` and `endTime` are not sent, the most recent klines are returned.

        Weight(IP): 2
      tags:
        - Market
      parameters:
        - $ref: '#/components/parameters/symbol'
        - name: interval
          in: query
          required: true
          description: kline intervals
          schema:
            type: string
            enum: ['1s','1m','3m','5m','15m','30m','1h','2h','4h','6h','8h','12h','1d','3d','1w','1M']
            example: '"1m"'
        - $ref: '#/components/parameters/startTime'
        - $ref: '#/components/parameters/endTime'
        - name: timeZone
          in: query
          required: false
          description: |-
            Default: 0 (UTC)
          schema:
            type: string
        - $ref: '#/components/parameters/limit'
      responses:
        '200':
          description: Kline data
          content:
            application/json:
              schema:
                type: array
                items:
                  type: array
                  items:
                    oneOf:
                      - type: integer
                        format: int64
                      - type: string
                    minItems: 12
                    maxItems: 12
                  example:
                    - 1499040000000
                    - "0.01634790"
                    - "0.80000000"
                    - "0.01575800"
                    - "0.01577100"
                    - "148976.11427815"
                    - 1499644799999
                    - "2434.19055334"
                    - 308
                    - "1756.87402397"
                    - "28.46694368"
                    - "17928899.62484339"
        '400':
          description: Bad Request
          content:
            application/json:
              schema:
                $ref: '#/components/schemas/error'
  /api/v3/uiKlines:
    get:
      summary: UIKlines
      description: |-
        The request is similar to klines having the same parameters and response.

        uiKlines return modified kline data, optimized for presentation of candlestick charts.

        Weight(IP): 2
      tags:
        - Market
      parameters:
        - $ref: '#/components/parameters/symbol'
        - name: interval
          in: query
          required: true
          description: kline intervals
          schema:
            type: string
            enum: ['1s','1m','3m','5m','15m','30m','1h','2h','4h','6h','8h','12h','1d','3d','1w','1M']
            example: '"1m"'
        - $ref: '#/components/parameters/startTime'
        - $ref: '#/components/parameters/endTime'
        - name: timeZone
          in: query
          required: false
          description: |-
            Default: 0 (UTC)
          schema:
            type: string
        - $ref: '#/components/parameters/limit'
      responses:
        '200':
          description: UIKline data
          content:
            application/json:
              schema:
                type: array
                items:
                  type: array
                  items:
                    oneOf:
                      - type: integer
                        format: int64
                      - type: string
                    minItems: 12
                    maxItems: 12
                  example:
                    - 1499040000000
                    - "0.01634790"
                    - "0.80000000"
                    - "0.01575800"
                    - "0.01577100"
                    - "148976.11427815"
                    - 1499644799999
                    - "2434.19055334"
                    - 308
                    - "1756.87402397"
                    - "28.46694368"
                    - "0"
        '400':
          description: Bad Request
          content:
            application/json:
              schema:
                $ref: '#/components/schemas/error'
  /api/v3/avgPrice:
    get:
      summary: Current Average Price
      description: |-
        Current average price for a symbol.

        Weight(IP): 2
      tags:
        - Market
      parameters:
        - $ref: '#/components/parameters/symbol'
      responses:
        '200':
          description: Average price
          content:
            application/json:
              schema:
                type: object
                properties:
                  mins:
                    type: integer
                    format: int64
                    example: 5
                    description: Average price interval (in minutes)
                  price:
                    type: string
                    example: "9.35751834"
                    description: Average price
                  closeTime:
                    type: integer
                    format: int64
                    example: 1694061154503
                    description: Last trade time
                required:
                  - mins
                  - price
                  - closeTime
        '400':
          description: Bad Request
          content:
            application/json:
              schema:
                $ref: '#/components/schemas/error'
  /api/v3/ticker/24hr:
    get:
      summary: 24hr Ticker Price Change Statistics
      description: |-
        24 hour rolling window price change statistics. Careful when accessing this with no symbol.

        - If the symbol is not sent, tickers for all symbols will be returned in an array.

        Weight(IP):
        - `2` for a single symbol;
        - `80` when the symbol parameter is omitted;

      tags:
        - Market
      parameters:
        - $ref: '#/components/parameters/optionalSymbol'
        - $ref: '#/components/parameters/arraySymbols'
        - $ref: '#/components/parameters/tickerType'
      responses:
        '200':
          description: 24hr ticker
          content:
            application/json:
              schema:
                oneOf:
                  - $ref: '#/components/schemas/ticker'
                  - $ref: '#/components/schemas/tickerList'
        '400':
          description: Bad Request
          content:
            application/json:
              schema:
                $ref: '#/components/schemas/error'
  /api/v3/ticker/tradingDay:
    get:
      summary: Trading Day Ticker
      description: |-
        Price change statistics for a trading day.

        Notes:
        - Supported values for timeZone:
          - Hours and minutes (e.g. -1:00, 05:45)
          - Only hours (e.g. 0, 8, 4)

        Weight:
        - `4` for each requested symbol.
        - The weight for this request will cap at `200` once the number of symbols in the request is more than `50`.
      tags:
        - Market
      parameters:
        - $ref: '#/components/parameters/optionalSymbol'
        - $ref: '#/components/parameters/arraySymbols'
        - name: timeZone
          in: query
          required: false
          description: |-
            Default: 0 (UTC)
          schema:
            type: string
        - $ref: '#/components/parameters/tickerType'
      responses:
        '200':
          description: Trading day ticker
          content:
            application/json:
              schema:
                oneOf:
                  - $ref: '#/components/schemas/dayTicker'
                  - $ref: '#/components/schemas/dayTickerList'
        '400':
          description: Bad Request
          content:
            application/json:
              schema:
                $ref: '#/components/schemas/error'
  /api/v3/ticker/price:
    get:
      summary: Symbol Price Ticker
      description: |-
        Latest price for a symbol or symbols.

        - If the symbol is not sent, prices for all symbols will be returned in an array.

        Weight(IP):
        - `2` for a single symbol;
        - `4` when the symbol parameter is omitted;
      tags:
        - Market
      parameters:
        - $ref: '#/components/parameters/optionalSymbol'
        - $ref: '#/components/parameters/arraySymbols'
      responses:
        '200':
          description: Price ticker
          content:
            application/json:
              schema:
                oneOf:
                  - $ref: '#/components/schemas/priceTicker'
                  - $ref: '#/components/schemas/priceTickerList'
        '400':
          description: Bad Request
          content:
            application/json:
              schema:
                $ref: '#/components/schemas/error'
  /api/v3/ticker/bookTicker:
    get:
      summary: Symbol Order Book Ticker
      description: |-
        Best price/qty on the order book for a symbol or symbols.

        - If the symbol is not sent, bookTickers for all symbols will be returned in an array.

        Weight(IP):
        - `2` for a single symbol;
        - `4` when the symbol parameter is omitted;
      tags:
        - Market
      parameters:
        - $ref: '#/components/parameters/optionalSymbol'
        - $ref: '#/components/parameters/arraySymbols'
      responses:
        '200':
          description: Order book ticker
          content:
            application/json:
              schema:
                oneOf:
                  - $ref: '#/components/schemas/bookTicker'
                  - $ref: '#/components/schemas/bookTickerList'
        '400':
          description: Bad Request
          content:
            application/json:
              schema:
                $ref: '#/components/schemas/error'
  /api/v3/ticker:
    get:
      summary: Rolling window price change statistics
      description: |-
        The window used to compute statistics is typically slightly wider than requested windowSize.

        openTime for /api/v3/ticker always starts on a minute, while the closeTime is the current time of the request. As such, the effective window might be up to 1 minute wider than requested.

        E.g. If the closeTime is 1641287867099 (January 04, 2022 09:17:47:099 UTC) , and the windowSize is 1d. the openTime will be: 1641201420000 (January 3, 2022, 09:17:00 UTC)

        Weight(IP): 4 for each requested symbol regardless of windowSize.

        The weight for this request will cap at 200 once the number of symbols in the request is more than 50.
      tags:
        - Market
      parameters:
        - $ref: '#/components/parameters/optionalSymbol'
        - $ref: '#/components/parameters/arraySymbols'
        - name: windowSize
          in: query
          description: |-
            Defaults to 1d if no parameter provided.
            Supported windowSize values:
            1m,2m....59m for minutes
            1h, 2h....23h - for hours
            1d...7d - for days.

            Units cannot be combined (e.g. 1d2h is not allowed)
          schema:
            type: string
        - name: type
          in: query
          description: |-
            Supported values: FULL or MINI.
            If none provided, the default is FULL
          schema:
            type: string
      responses:
        '200':
          description: Rolling price ticker
          content:
            application/json:
              schema:
                type: object
                properties:
                  symbol:
                    type: string
                    example: BNBBTC
                  priceChange:
                    type: string
                    example: '-8.00000000'
                  priceChangePercent:
                    type: string
                    example: '-88.889'
                  weightedAvgPrice:
                    type: string
                    example: '2.60427807'
                  openPrice:
                    type: string
                    example: '9.00000000'
                  highPrice:
                    type: string
                    example: '9.00000000'
                  lowPrice:
                    type: string
                    example: '1.00000000'
                  lastPrice:
                    type: string
                    example: '1.00000000'
                  volume:
                    type: string
                    example: '187.00000000'
                  quoteVolume:
                    type: string
                    example: '487.00000000'
                  openTime:
                    type: integer
                    format: int64
                    example: 1641859200000
                  closeTime:
                    type: integer
                    format: int64
                    example: 1642031999999
                  firstId:
                    type: integer
                    format: int64
                    example: 0
                  lastId:
                    type: integer
                    format: int64
                    example: 60
                  count:
                    type: integer
                    format: int64
                    example: 61
                required:
                  - symbol
                  - priceChange
                  - priceChangePercent
                  - weightedAvgPrice
                  - openPrice
                  - highPrice
                  - lowPrice
                  - lastPrice
                  - volume
                  - quoteVolume
                  - openTime
                  - closeTime
                  - firstId
                  - lastId
                  - count
        '400':
          description: Bad Request
          content:
            application/json:
              schema:
                $ref: '#/components/schemas/error'
  /api/v3/order/test:
    post:
      summary: Test New Order (TRADE)
      description: |-
        Test new order creation and signature/recvWindow long.
        Creates and validates a new order but does not send it into the matching engine.

        Weight(IP):
          - Without computeCommissionRates: `1`
          - With computeCommissionRates: `20`
      tags:
        - Trade
      parameters:
        - $ref: '#/components/parameters/symbol'
        - $ref: '#/components/parameters/side'
        - $ref: '#/components/parameters/orderType'
        - $ref: '#/components/parameters/timeInForce'
        - $ref: '#/components/parameters/optionalQuantity'
        - $ref: '#/components/parameters/quoteOrderQty'
        - $ref: '#/components/parameters/optionalPrice'
        - $ref: '#/components/parameters/newClientOrderId'
        - $ref: '#/components/parameters/strategyId'
        - $ref: '#/components/parameters/strategyType'
        - $ref: '#/components/parameters/stopPrice'
        - $ref: '#/components/parameters/optionalTrailingDelta'
        - $ref: '#/components/parameters/icebergQty'
        - $ref: '#/components/parameters/newOrderRespType'
        - $ref: '#/components/parameters/recvWindow'
        - name: computeCommissionRates
          in: query
          required: false
          description: |-
            Default: false
          schema:
            type: boolean
            example: false
        - $ref: '#/components/parameters/timestamp'
        - $ref: '#/components/parameters/signature'
      security:
        - ApiKeyAuth: []
      responses:
        '200':
          description: OK
          content:
            application/json:
              schema:
                type: object
        '400':
          description: Bad Request
          content:
            application/json:
              schema:
                $ref: '#/components/schemas/error'
        '401':
          description: Unauthorized Request
          content:
            application/json:
              schema:
                $ref: '#/components/schemas/error'
  /api/v3/order:
    get:
      summary: Query Order (USER_DATA)
      description: |-
        Check an order's status.

        - Either `orderId` or `origClientOrderId` must be sent.
        - For some historical orders `cummulativeQuoteQty` will be < 0, meaning the data is not available at this time.

        Weight(IP): 4
      tags:
        - Trade
      parameters:
        - $ref: '#/components/parameters/symbol'
        - $ref: '#/components/parameters/orderId'
        - $ref: '#/components/parameters/origClientOrderId'
        - $ref: '#/components/parameters/recvWindow'
        - $ref: '#/components/parameters/timestamp'
        - $ref: '#/components/parameters/signature'
      security:
        - ApiKeyAuth: []
      responses:
        '200':
          description: Order details
          content:
            application/json:
              schema:
                $ref: '#/components/schemas/orderDetails'
        '400':
          description: Bad Request
          content:
            application/json:
              schema:
                $ref: '#/components/schemas/error'
        '401':
          description: Unauthorized Request
          content:
            application/json:
              schema:
                $ref: '#/components/schemas/error'
    post:
      summary: New Order (TRADE)
      description: |-
        Send in a new order.

        - `LIMIT_MAKER` are `LIMIT` orders that will be rejected if they would immediately match and trade as a taker.
        - `STOP_LOSS` and `TAKE_PROFIT` will execute a `MARKET` order when the `stopPrice` is reached.
        - Any `LIMIT` or `LIMIT_MAKER` type order can be made an iceberg order by sending an `icebergQty`.
        - Any order with an `icebergQty` MUST have `timeInForce` set to `GTC`.
        - `MARKET` orders using `quantity` specifies how much a user wants to buy or sell based on the market price.
        - `MARKET` orders using `quoteOrderQty` specifies the amount the user wants to spend (when buying) or receive (when selling) of the quote asset; the correct quantity will be determined based on the market liquidity and `quoteOrderQty`.
        - `MARKET` orders using `quoteOrderQty` will not break `LOT_SIZE` filter rules; the order will execute a quantity that will have the notional value as close as possible to `quoteOrderQty`.
        - same `newClientOrderId` can be accepted only when the previous one is filled, otherwise the order will be rejected.

        Trigger order price rules against market price for both `MARKET` and `LIMIT` versions:

        - Price above market price: `STOP_LOSS` `BUY`, `TAKE_PROFIT` `SELL`
        - Price below market price: `STOP_LOSS` `SELL`, `TAKE_PROFIT` `BUY`


        Weight(IP): 1
      tags:
        - Trade
      parameters:
        - $ref: '#/components/parameters/symbol'
        - $ref: '#/components/parameters/side'
        - $ref: '#/components/parameters/orderType'
        - $ref: '#/components/parameters/timeInForce'
        - $ref: '#/components/parameters/optionalQuantity'
        - $ref: '#/components/parameters/quoteOrderQty'
        - $ref: '#/components/parameters/optionalPrice'
        - $ref: '#/components/parameters/newClientOrderId'
        - $ref: '#/components/parameters/strategyId'
        - $ref: '#/components/parameters/strategyType'
        - $ref: '#/components/parameters/stopPrice'
        - $ref: '#/components/parameters/optionalTrailingDelta'
        - $ref: '#/components/parameters/icebergQty'
        - $ref: '#/components/parameters/newOrderRespType'
        - $ref: '#/components/parameters/selfTradePreventionMode'
        - $ref: '#/components/parameters/recvWindow'
        - $ref: '#/components/parameters/timestamp'
        - $ref: '#/components/parameters/signature'
      security:
        - ApiKeyAuth: []
      responses:
        '200':
          description: Order result
          content:
            application/json:
              schema:
                oneOf:
                  - $ref: '#/components/schemas/orderResponseAck'
                  - $ref: '#/components/schemas/orderResponseResult'
                  - $ref: '#/components/schemas/orderResponseFull'
        '400':
          description: Bad Request
          content:
            application/json:
              schema:
                $ref: '#/components/schemas/error'
        '401':
          description: Unauthorized Request
          content:
            application/json:
              schema:
                $ref: '#/components/schemas/error'
    delete:
      summary: Cancel Order (TRADE)
      description: |-
        Cancel an active order.

        Either `orderId` or `origClientOrderId` must be sent.

        Weight(IP): 1
      tags:
        - Trade
      parameters:
        - $ref: '#/components/parameters/symbol'
        - $ref: '#/components/parameters/orderId'
        - $ref: '#/components/parameters/origClientOrderId'
        - $ref: '#/components/parameters/newClientOrderId'
        - $ref: '#/components/parameters/cancelRestrictions'
        - $ref: '#/components/parameters/recvWindow'
        - $ref: '#/components/parameters/timestamp'
        - $ref: '#/components/parameters/signature'
      security:
        - ApiKeyAuth: []
      responses:
        '200':
          description: Cancelled order
          content:
            application/json:
              schema:
                $ref: '#/components/schemas/order'
        '400':
          description: Bad Request
          content:
            application/json:
              schema:
                $ref: '#/components/schemas/error'
        '401':
          description: Unauthorized Request
          content:
            application/json:
              schema:
                $ref: '#/components/schemas/error'
  /api/v3/order/cancelReplace:
    post:
      summary: Cancel an Existing Order and Send a New Order (Trade)
      description: |-
        Cancels an existing order and places a new order on the same symbol.

        Filters and Order Count are evaluated before the processing of the cancellation and order placement occurs.

        A new order that was not attempted (i.e. when newOrderResult: NOT_ATTEMPTED), will still increase the order count by 1.

        Weight(IP): 1
      tags:
        - Trade
      parameters:
        - $ref: '#/components/parameters/symbol'
        - $ref: '#/components/parameters/side'
        - $ref: '#/components/parameters/orderType'
        - name: cancelReplaceMode
          in: query
          required: true
          description: |-
            - `STOP_ON_FAILURE` If the cancel request fails, the new order placement will not be attempted.
            - `ALLOW_FAILURES` If new order placement will be attempted even if cancel request fails.
          schema:
            type: string
            example: "STOP_ON_FAILURE"
        - $ref: '#/components/parameters/cancelRestrictions'
        - $ref: '#/components/parameters/timeInForce'
        - $ref: '#/components/parameters/optionalQuantity'
        - $ref: '#/components/parameters/quoteOrderQty'
        - $ref: '#/components/parameters/optionalPrice'
        - name: cancelNewClientOrderId
          in: query
          description: Used to uniquely identify this cancel. Automatically generated by default
          schema:
            type: string
        - name: cancelOrigClientOrderId
          in: query
          description: Either the cancelOrigClientOrderId or cancelOrderId must be provided. If both are provided, cancelOrderId takes precedence.
          schema:
            type: string
        - name: cancelOrderId
          in: query
          description: Either the cancelOrigClientOrderId or cancelOrderId must be provided. If both are provided, cancelOrderId takes precedence.
          schema:
            type: integer
            format: int64
            example: 12
        - $ref: '#/components/parameters/newClientOrderId'
        - $ref: '#/components/parameters/strategyId'
        - $ref: '#/components/parameters/strategyType'
        - $ref: '#/components/parameters/stopPrice'
        - $ref: '#/components/parameters/optionalTrailingDelta'
        - $ref: '#/components/parameters/icebergQty'
        - $ref: '#/components/parameters/newOrderRespType'
        - $ref: '#/components/parameters/selfTradePreventionMode'
        - $ref: '#/components/parameters/recvWindow'
        - $ref: '#/components/parameters/timestamp'
        - $ref: '#/components/parameters/signature'
      security:
        - ApiKeyAuth: []
      responses:
        '200':
          description: Operation details
          content:
            application/json:
              schema:
                type: object
                properties:
                  cancelResult:
                    type: string
                    example: SUCCESS
                  newOrderResult:
                    type: string
                    example: SUCCESS
                  cancelResponse:
                    type: object
                    properties:
                      symbol:
                        type: string
                        example: BTCUSDT
                      origClientOrderId:
                        type: string
                        example: DnLo3vTAQcjha43lAZhZ0y
                      orderId:
                        type: integer
                        format: int64
                        example: 9
                      orderListId:
                        type: integer
                        format: int64
                        example: -1
                      clientOrderId:
                        type: string
                        example: osxN3JXAtJvKvCqGeMWMVR
                      price:
                        type: string
                        example: '0.01000000'
                      origQty:
                        type: string
                        example: '0.000100'
                      executedQty:
                        type: string
                        example: '0.00000000'
                      cummulativeQuoteQty:
                        type: string
                        example: '0.00000000'
                      status:
                        type: string
                        example: CANCELED
                      timeInForce:
                        type: string
                        example: GTC
                      type:
                        type: string
                        example: LIMIT
                      side:
                        type: string
                        example: SELL
                      selfTradePreventionMode:
                        type: string
                        example: NONE
                      transactTime:
                        type: integer
                        format: int64
                        example: 1507725176595
                    required:
                      - symbol
                      - origClientOrderId
                      - orderId
                      - orderListId
                      - clientOrderId
                      - price
                      - origQty
                      - executedQty
                      - cummulativeQuoteQty
                      - status
                      - timeInForce
                      - type
                      - side
                      - selfTradePreventionMode
                  newOrderResponse:
                    type: object
                    properties:
                      symbol:
                        type: string
                        example: BTCUSDT
                      orderId:
                        type: integer
                        format: int64
                        example: 10
                      orderListId:
                        type: integer
                        format: int64
                        example: -1
                      clientOrderId:
                        type: string
                        example: wOceeeOzNORyLiQfw7jd8S
                      transactTime:
                        type: integer
                        format: int64
                        example: 1652928801803
                      price:
                        type: string
                        example: '0.02000000'
                      origQty:
                        type: string
                        example: '0.040000'
                      executedQty:
                        type: string
                        example: '0.00000000'
                      cummulativeQuoteQty:
                        type: string
                        example: '0.00000000'
                      status:
                        type: string
                        example: NEW
                      timeInForce:
                        type: string
                        example: GTC
                      type:
                        type: string
                        example: LIMIT
                      side:
                        type: string
                        example: BUY
                      workingTime:
                        type: integer
                        format: int64
                        example: 1669277163808
                      fills:
                        type: array
                        items:
                          type: string
                        maxItems: 0
                      selfTradePreventionMode:
                        type: string
                        example: NONE
                    required:
                      - symbol
                      - orderId
                      - orderListId
                      - clientOrderId
                      - transactTime
                      - price
                      - origQty
                      - executedQty
                      - cummulativeQuoteQty
                      - status
                      - timeInForce
                      - type
                      - side
                      - workingTime
                      - fills
                      - selfTradePreventionMode
                required:
                  - cancelResult
                  - newOrderResult
                  - cancelResponse
                  - newOrderResponse
        '400':
          description: Bad Request
          content:
            application/json:
              schema:
                $ref: '#/components/schemas/error'
        '401':
            description: Unauthorized Request
            content:
              application/json:
                schema:
                  $ref: '#/components/schemas/error'
  /api/v3/openOrders:
    get:
      summary: Current Open Orders (USER_DATA)
      description: |-
        Get all open orders on a symbol. Careful when accessing this with no symbol.

        Weight(IP):
        - `6` for a single symbol;
        - `80` when the symbol parameter is omitted;
      tags:
        - Trade
      parameters:
        - $ref: '#/components/parameters/optionalSymbol'
        - $ref: '#/components/parameters/recvWindow'
        - $ref: '#/components/parameters/timestamp'
        - $ref: '#/components/parameters/signature'
      security:
        - ApiKeyAuth: []
      responses:
        '200':
          description: Current open orders
          content:
            application/json:
              schema:
                type: array
                items:
                  $ref: '#/components/schemas/orderDetails'
        '400':
          description: Bad Request
          content:
            application/json:
              schema:
                $ref: '#/components/schemas/error'
        '401':
            description: Unauthorized Request
            content:
              application/json:
                schema:
                  $ref: '#/components/schemas/error'
    delete:
      summary: Cancel all Open Orders on a Symbol (TRADE)
      description: |-
        Cancels all active orders on a symbol.
        This includes OCO orders.

        Weight(IP): 1
      tags:
        - Trade
      parameters:
        - $ref: '#/components/parameters/symbol'
        - $ref: '#/components/parameters/recvWindow'
        - $ref: '#/components/parameters/timestamp'
        - $ref: '#/components/parameters/signature'
      security:
        - ApiKeyAuth: []
      responses:
        '200':
          description: Cancelled orders
          content:
            application/json:
              schema:
                type: array
                items:
                  anyOf:
                    - $ref: '#/components/schemas/order'
                    - $ref: '#/components/schemas/ocoOrder'
        '400':
          description: Bad Request
          content:
            application/json:
              schema:
                $ref: '#/components/schemas/error'
        '401':
            description: Unauthorized Request
            content:
              application/json:
                schema:
                  $ref: '#/components/schemas/error'
  /api/v3/allOrders:
    get:
      summary: All Orders (USER_DATA)
      description: |-
        Get all account orders; active, canceled, or filled..

        - If `orderId` is set, it will get orders >= that `orderId`. Otherwise most recent orders are returned.
        - For some historical orders `cummulativeQuoteQty` will be < 0, meaning the data is not available at this time.
        - If `startTime` and/or `endTime` provided, `orderId` is not required

        Weight(IP): 20
      tags:
        - Trade
      parameters:
        - $ref: '#/components/parameters/symbol'
        - $ref: '#/components/parameters/orderId'
        - $ref: '#/components/parameters/startTime'
        - $ref: '#/components/parameters/endTime'
        - $ref: '#/components/parameters/limit'
        - $ref: '#/components/parameters/recvWindow'
        - $ref: '#/components/parameters/timestamp'
        - $ref: '#/components/parameters/signature'
      security:
        - ApiKeyAuth: []
      responses:
        '200':
          description: Current open orders
          content:
            application/json:
              schema:
                type: array
                items:
                  $ref: '#/components/schemas/orderDetails'
        '400':
          description: Bad Request
          content:
            application/json:
              schema:
                $ref: '#/components/schemas/error'
        '401':
            description: Unauthorized Request
            content:
              application/json:
                schema:
                  $ref: '#/components/schemas/error'
  /api/v3/orderList/oco:
    post:
      summary: New Order list - OCO (TRADE)
      description: |-
        Send in an one-cancels-the-other (OCO) pair, where activation of one order immediately cancels the other.

        - An `OCO` has 2 orders called the above order and below order.
        - One of the orders must be a `LIMIT_MAKER` order and the other must be `STOP_LOSS` or`STOP_LOSS_LIMIT` order.
        - Price restrictions:
            - If the `OCO` is on the `SELL` side: `LIMIT_MAKER` price > Last Traded Price > stopPrice
            - If the `OCO` is on the `BUY` side: `LIMIT_MAKER` price < Last Traded Price < stopPrice
        - OCOs add 2 orders to the unfilled order count, `EXCHANGE_MAX_ORDERS` filter, and the `MAX_NUM_ORDERS` filter.

        Weight(IP): 1
      tags:
        - Trade
      parameters:
        - $ref: '#/components/parameters/symbol'
        - name: listClientOrderId
          in: query
          description: |-
            Arbitrary unique ID among open order lists. Automatically generated if not sent.
            A new order list with the same `listClientOrderId` is accepted only when the previous one is filled or completely expired.
            `listClientOrderId` is distinct from the `aboveClientOrderId` and the `belowCLientOrderId`.
          schema:
            type: string
        - $ref: '#/components/parameters/side'
        - $ref: '#/components/parameters/quantity'
        - name: aboveType
          in: query
          required: true
          description: |-
            Supported values : `STOP_LOSS_LIMIT`, `STOP_LOSS`, `LIMIT_MAKER`
          schema:
            type: string
        - name: aboveClientOrderId
          in: query
          description: |-
            Arbitrary unique ID among open orders for the above order. Automatically generated if not sent
          schema:
            type: string
        - name: aboveIcebergQty
          in: query
          description: |-
            Note that this can only be used if `aboveTimeInForce` is `GTC`.
          schema:
            type: number
            format: double
        - name: abovePrice
          in: query
          schema:
            type: number
            format: double
        - name: aboveStopPrice
          in: query
          description: |-
            Can be used if `aboveType` is `STOP_LOSS` or `STOP_LOSS_LIMIT`.
            Either `aboveStopPrice` or `aboveTrailingDelta` or both, must be specified.
          schema:
            type: number
            format: double
        - name: aboveTrailingDelta
          in: query
          schema:
            type: number
            format: double
        - name: aboveTimeInForce
          in: query
          description: |-
            Required if the `aboveType` is `STOP_LOSS_LIMIT`.
          schema:
            type: string
            enum: [GTC,IOC,FOK]
            example: 'GTC'
        - name: aboveStrategyId
          in: query
          description: |-
            Arbitrary numeric value identifying the above order within an order strategy.
          schema:
            type: number
            format: double
        - name: aboveStrategyType
          in: query
          description: |-
            Arbitrary numeric value identifying the above order strategy.
            Values smaller than 1000000 are reserved and cannot be used.
          schema:
            type: integer
            format: int64
        - name: belowType
          in: query
          required: true
          description: |-
            Supported values : `STOP_LOSS_LIMIT`, `STOP_LOSS`, `LIMIT_MAKER`
          schema:
            type: string
        - name: belowClientOrderId
          in: query
          description: |-
            Arbitrary unique ID among open orders for the below order. Automatically generated if not sent
          schema:
            type: string
        - name: belowIcebergQty
          in: query
          description: |-
            Note that this can only be used if `belowTimeInForce` is `GTC`.
          schema:
            type: number
            format: double
        - name: belowPrice
          in: query
          description: |-
            Can be used if `belowType` is `STOP_LOSS_LIMIT` or `LIMIT_MAKER` to specify the limit price.
          schema:
            type: number
            format: double
        - name: belowStopPrice
          in: query
          description: |-
            Can be used if `belowType` is `STOP_LOSS` or `STOP_LOSS_LIMIT`.
            Either `belowStopPrice` or `belowTrailingDelta` or both, must be specified.
          schema:
            type: number
            format: double
        - name: belowTrailingDelta
          in: query
          schema:
            type: number
            format: double
        - name: belowTimeInForce
          in: query
          description: |-
            Required if the `belowType` is `STOP_LOSS_LIMIT`.
          schema:
            type: string
            enum: [GTC,IOC,FOK]
            example: 'GTC'
        - name: belowStrategyId
          in: query
          description: |-
            Arbitrary numeric value identifying the below order within an order strategy.
          schema:
            type: number
            format: double
        - name: belowStrategyType
          in: query
          description: |-
            Arbitrary numeric value identifying the below order strategy.
            Values smaller than 1000000 are reserved and cannot be used.
          schema:
            type: integer
            format: int64
        - $ref: '#/components/parameters/newOrderRespType'
        - $ref: '#/components/parameters/selfTradePreventionMode'
        - $ref: '#/components/parameters/recvWindow'
        - $ref: '#/components/parameters/timestamp'
        - $ref: '#/components/parameters/signature'
      security:
        - ApiKeyAuth: []
      responses:
        '200':
          description: New OCO details
          content:
            application/json:
              schema:
                type: object
                properties:
                  orderListId:
                    type: integer
                    format: int64
                    example: 1
                  contingencyType:
                    type: string
                    example: "OCO"
                  listStatusType:
                    type: string
                    example: "EXEC_STARTED"
                  listOrderStatus:
                    type: string
                    example: "EXECUTING"
                  listClientOrderId:
                    type: string
                    example: "lH1YDkuQKWiXVXHPSKYEIp"
                  transactionTime:
                    type: integer
                    format: int64
                    example: 1710485608839
                  symbol:
                    type: string
                    example: "LTCBTC"
                  orders:
                    type: array
                    items:
                      type: object
                      properties:
                        symbol:
                          type: string
                        orderId:
                          type: integer
                          format: int64
                        clientOrderId:
                          type: string
                      required:
                        - symbol
                        - orderId
                        - clientOrderId
                      example:
                        - symbol: "LTCBTC"
                          orderId: 10
                          clientOrderId: "44nZvqpemY7sVYgPYbvPih"
                        - symbol: "LTCBTC"
                          orderId: 11
                          clientOrderId: "NuMp0nVYnciDiFmVqfpBqK"
                  orderReports:
                    type: array
                    items:
                      type: object
                      properties:
                        symbol:
                          type: string
                        orderId:
                          type: integer
                          format: int64
                        orderListId:
                          type: integer
                          format: int64
                        clientOrderId:
                          type: string
                        transactTime:
                          type: integer
                          format: int64
                        price:
                          type: string
                        origQty:
                          type: string
                        executedQty:
                          type: string
                        cummulativeQuoteQty:
                          type: string
                        status:
                          type: string
                        timeInForce:
                          type: string
                        type:
                          type: string
                        side:
                          type: string
                        stopPrice:
                          type: string
                        workingTime:
                          type: integer
                          format: int64
                        selfTradePreventionMode:
                          type: string
                      required:
                        - symbol
                        - orderId
                        - orderListId
                        - clientOrderId
                        - transactTime
                        - price
                        - origQty
                        - executedQty
                        - cummulativeQuoteQty
                        - status
                        - timeInForce
                        - type
                        - side
                        - stopPrice
                        - workingTime
                        - selfTradePreventionMode
                    example:
                      - symbol: "LTCBTC"
                        orderId: 10
                        orderListId: 1
                        clientOrderId: "44nZvqpemY7sVYgPYbvPih"
                        transactTime: 1710485608839
                        price: "1.000000"
                        origQty: "5.00000000"
                        executedQty: "0.000000"
                        cummulativeQuoteQty: "0.000000"
                        status: "NEW"
                        timeInForce: "GTC"
                        type: "STOP_LOSS_LIMIT"
                        side: "SELL"
                        stopPrice: "1.00000000"
                        workingTime: -1
                        icebergQty: "1.00000000"
                        selfTradePreventionMode: "NONE"
                      - symbol: "LTCBTC"
                        orderId: 11
                        orderListId: 1
                        clientOrderId: "NuMp0nVYnciDiFmVqfpBqK"
                        transactTime: 1710485608839
                        price: "3.00000000"
                        origQty: "5.00000000"
                        executedQty: "0.000000"
                        cummulativeQuoteQty: "0.000000"
                        status: "NEW"
                        timeInForce: "GTC"
                        type: "LIMIT_MAKER"
                        side: "SELL"
                        workingTime: 1710485608839
                        selfTradePreventionMode: "NONE"
                required:
                  - orderListId
                  - contingencyType
                  - listStatusType
                  - listOrderStatus
                  - listClientOrderId
                  - transactionTime
                  - symbol
                  - orders
                  - orderReports
        '400':
          description: Bad Request
          content:
            application/json:
              schema:
                $ref: '#/components/schemas/error'
        '401':
            description: Unauthorized Request
            content:
              application/json:
                schema:
                  $ref: '#/components/schemas/error'
  /api/v3/orderList/oto:
    post:
      summary: New Order List - OTO (TRADE)
      description: |-
        Places an `OTO`.
        - An `OTO` (One-Triggers-the-Other) is an order list comprised of 2 orders.
        - The first order is called the working order and must be `LIMIT` or `LIMIT_MAKER`. Initially, only the working order goes on the order book.
        - The second order is called the pending order. It can be any order type except for `MARKET` orders using parameter `quoteOrderQty`. The pending order is only placed on the order book when the working order gets fully filled.
        - If either the working order or the pending order is cancelled individually, the other order in the order list will also be canceled or expired.
        - When the order list is placed, if the working order gets immediately fully filled, the placement response will show the working order as `FILLED` but the pending order will still appear as `PENDING_NEW`. You need to query the status of the pending order again to see its updated status.
        - OTOs add 2 orders to the unfilled order count, `EXCHANGE_MAX_NUM_ORDERS` filter and `MAX_NUM_ORDERS` filter.

        Weight: 1
      tags:
        - Trade
      parameters:
        - $ref: '#/components/parameters/symbol'
        - name: listClientOrderId
          in: query
          description: |-
            Arbitrary unique ID among open order lists. Automatically generated if not sent.
            A new order list with the same `listClientOrderId` is accepted only when the previous one is filled or completely expired.
            `listClientOrderId` is distinct from the `workingClientOrderId` and the `pendingClientOrderId`.
          schema:
            type: string
        - $ref: '#/components/parameters/ocoNewOrderRespType'
        - $ref: '#/components/parameters/selfTradePreventionMode'
        - $ref: '#/components/parameters/workingType'
        - $ref: '#/components/parameters/workingSide'
        - $ref: '#/components/parameters/workingClientOrderId'
        - $ref: '#/components/parameters/workingPrice'
        - $ref: '#/components/parameters/workingQuantity'
        - $ref: '#/components/parameters/workingIcebergQty'
        - $ref: '#/components/parameters/workingTimeInForce'
        - name: workingStrategyId
          in: query
          description: |-
            Arbitrary numeric value identifying the working order within an order strategy.
          schema:
            type: number
            format: double
        - name: workingStrategyType
          in: query
          description: |-
            Arbitrary numeric value identifying the working order strategy.
            Values smaller than 1000000 are reserved and cannot be used.
          schema:
            type: integer
            format: int64
        - $ref: '#/components/parameters/pendingType'
        - $ref: '#/components/parameters/pendingSide'
        - $ref: '#/components/parameters/pendingClientOrderId'
        - $ref: '#/components/parameters/pendingPrice'
        - $ref: '#/components/parameters/pendingStopPrice'
        - $ref: '#/components/parameters/pendingTrailingDelta'
        - $ref: '#/components/parameters/pendingQuantity'
        - $ref: '#/components/parameters/pendingIcebergQty'
        - $ref: '#/components/parameters/pendingTimeInForce'
        - name: pendingStrategyId
          in: query
          description: |-
            Arbitrary numeric value identifying the pending order within an order strategy.
          schema:
            type: number
            format: double
        - name: pendingStrategyType
          in: query
          description: |-
            Arbitrary numeric value identifying the pending order strategy.
            Values smaller than 1000000 are reserved and cannot be used.
          schema:
            type: integer
            format: int64
        - $ref: '#/components/parameters/timestamp'
        - $ref: '#/components/parameters/signature'
      security:
        - ApiKeyAuth: []
      responses:
        '200':
          description: New OTO details
          content:
            application/json:
              schema:
                type: object
                properties:
                  orderListId:
                    type: integer
                    format: int64
                    example: 0
                  contingencyType:
                    type: string
                    example: "OTO"
                  listStatusType:
                    type: string
                    example: "EXEC_STARTED"
                  listOrderStatus:
                    type: string
                    example: "EXECUTING"
                  listClientOrderId:
                    type: string
                    example: "yl2ERtcar1o25zcWtqVBTC"
                  transactionTime:
                    type: integer
                    format: int64
                    example: 1712289389158
                  symbol:
                    type: string
                    example: "LTCBTC"
                  orders:
                    type: array
                    items:
                      type: object
                      properties:
                        symbol:
                          type: string
                        orderId:
                          type: integer
                          format: int64
                        clientOrderId:
                          type: string
                      required:
                        - symbol
                        - orderId
                        - clientOrderId
                      example:
                        - symbol: "LTCBTC"
                          orderId: 4
                          clientOrderId: "Bq17mn9fP6vyCn75Jw1xya"
                        - symbol: "LTCBTC"
                          orderId: 5
                          clientOrderId: "arLFo0zGJVDE69cvGBaU0d"
                  orderReports:
                    type: array
                    items:
                      type: object
                      properties:
                        symbol:
                          type: string
                        orderId:
                          type: integer
                          format: int64
                        orderListId:
                          type: integer
                          format: int64
                        clientOrderId:
                          type: string
                        transactTime:
                          type: integer
                          format: int64
                        price:
                          type: string
                        origQty:
                          type: string
                        executedQty:
                          type: string
                        cummulativeQuoteQty:
                          type: string
                        status:
                          type: string
                        timeInForce:
                          type: string
                        type:
                          type: string
                        side:
                          type: string
                        workingTime:
                          type: integer
                          format: int64
                        selfTradePreventionMode:
                          type: string
                      required:
                        - symbol
                        - orderId
                        - orderListId
                        - clientOrderId
                        - transactTime
                        - price
                        - origQty
                        - executedQty
                        - cummulativeQuoteQty
                        - status
                        - timeInForce
                        - type
                        - side
                        - workingTime
                        - selfTradePreventionMode
                      example:
                        - symbol: "LTCBTC"
                          orderId: 4
                          orderListId: 0
                          clientOrderId: "Bq17mn9fP6vyCn75Jw1xya"
                          transactTime: 1712289389158
                          price: "1.000000"
                          origQty: "1.00000000"
                          executedQty: "0.00000000"
                          cummulativeQuoteQty: "0.00000000"
                          status: "NEW"
                          timeInForce: "GTC"
                          type: "LIMIT"
                          side: "SELL"
                          workingTime: 1712289389158
                          selfTradePreventionMode: "NONE"
                        - symbol: "LTCBTC"
                          orderId: 5
                          orderListId: 0
                          clientOrderId: "arLFo0zGJVDE69cvGBaU0d"
                          transactTime: 1712289389158
                          price: "0.00000000"
                          origQty: "5.00000000"
                          executedQty: "0.00000000"
                          cummulativeQuoteQty: "0.00000000"
                          status: "PENDING_NEW"
                          timeInForce: "GTC"
                          type: "MARKET"
                          side: "BUY"
                          workingTime: -1
                          selfTradePreventionMode: "NONE"
                required:
                  - orderListId
                  - contingencyType
                  - listStatusType
                  - listOrderStatus
                  - listClientOrderId
                  - transactionTime
                  - symbol
                  - orders
                  - orderReports
        '400':
          description: Bad Request
          content:
            application/json:
              schema:
                $ref: '#/components/schemas/error'
        '401':
            description: Unauthorized Request
            content:
              application/json:
                schema:
                  $ref: '#/components/schemas/error'
  /api/v3/orderList/otoco:
    post:
      summary: New Order List - OTOCO (TRADE)
      description: |-
        Place an `OTOCO`.
        - An `OTOCO` (One-Triggers-One-Cancels-the-Other) is an order list comprised of 3 orders.
        - The first order is called the working order and must be `LIMIT` or `LIMIT_MAKER`. Initially, only the working order goes on the order book.
          - The behavior of the working order is the same as the `OTO`.
        - `OTOCO` has 2 pending orders (pending above and pending below), forming an `OCO` pair. The pending orders are only placed on the order book when the working order gets fully filled.
          - The rules of the pending above and pending below follow the same rules as the Order List `OCO`.
        - OTOCOs add 3 orders against the unfilled order count, `EXCHANGE_MAX_NUM_ORDERS` filter, and `MAX_NUM_ORDERS` filter.

        Weight: 1
      tags:
        - Trade
      parameters:
        - $ref: '#/components/parameters/symbol'
        - name: listClientOrderId
          in: query
          description: |-
            Arbitrary unique ID among open order lists. Automatically generated if not sent.
            A new order list with the same `listClientOrderId` is accepted only when the previous one is filled or completely expired.
            `listClientOrderId` is distinct from the `workingClientOrderId` and the `pendingClientOrderId`.
          schema:
            type: string
        - $ref: '#/components/parameters/ocoNewOrderRespType'
        - $ref: '#/components/parameters/selfTradePreventionMode'
        - $ref: '#/components/parameters/workingType'
        - $ref: '#/components/parameters/workingSide'
        - $ref: '#/components/parameters/workingClientOrderId'
        - $ref: '#/components/parameters/workingPrice'
        - $ref: '#/components/parameters/workingQuantity'
        - $ref: '#/components/parameters/workingIcebergQty'
        - $ref: '#/components/parameters/workingTimeInForce'
        - name: workingStrategyId
          in: query
          description: |-
            Arbitrary numeric value identifying the working order within an order strategy.
          schema:
            type: number
            format: double
        - name: workingStrategyType
          in: query
          description: |-
            Arbitrary numeric value identifying the working order strategy.
            Values smaller than 1000000 are reserved and cannot be used.
          schema:
            type: integer
            format: int64
        - $ref: '#/components/parameters/pendingSide'
        - $ref: '#/components/parameters/pendingQuantity'
        - $ref: '#/components/parameters/pendingAboveType'
        - $ref: '#/components/parameters/pendingAboveClientOrderId'
        - $ref: '#/components/parameters/pendingAbovePrice'
        - $ref: '#/components/parameters/pendingAboveStopPrice'
        - $ref: '#/components/parameters/pendingAboveTrailingDelta'
        - $ref: '#/components/parameters/pendingAboveIcebergQty'
        - $ref: '#/components/parameters/pendingAboveTimeInForce'
        - name: pendingAboveStrategyId
          in: query
          description: |-
            Arbitrary numeric value identifying the pending above order within an order strategy.
          schema:
            type: number
            format: double
        - name: pendingAboveStrategyType
          in: query
          description: |-
            Arbitrary numeric value identifying the pending above order strategy.
            Values smaller than 1000000 are reserved and cannot be used.
          schema:
            type: integer
            format: int64
        - $ref: '#/components/parameters/pendingBelowType'
        - $ref: '#/components/parameters/pendingBelowClientOrderId'
        - $ref: '#/components/parameters/pendingBelowPrice'
        - $ref: '#/components/parameters/pendingBelowStopPrice'
        - $ref: '#/components/parameters/pendingBelowTrailingDelta'
        - $ref: '#/components/parameters/pendingBelowIcebergQty'
        - $ref: '#/components/parameters/pendingBelowTimeInForce'
        - name: pendingBelowStrategyId
          in: query
          description: |-
            Arbitrary numeric value identifying the pending below order within an order strategy.
          schema:
            type: number
            format: double
        - name: pendingBelowStrategyType
          in: query
          description: |-
            Arbitrary numeric value identifying the pending below order strategy.
            Values smaller than 1000000 are reserved and cannot be used.
          schema:
            type: integer
            format: int64
        - $ref: '#/components/parameters/recvWindow'
        - $ref: '#/components/parameters/timestamp'
        - $ref: '#/components/parameters/signature'
      security:
        - ApiKeyAuth: []
      responses:
        '200':
          description: New OTOCO details
          content:
            application/json:
              schema:
                type: object
                properties:
                  orderListId:
                    type: integer
                    format: int64
                    example: 1
                  contingencyType:
                    type: string
                    example: "OTOCO"
                  listStatusType:
                    type: string
                    example: "EXEC_STARTED"
                  listOrderStatus:
                    type: string
                    example: "EXECUTING"
                  listClientOrderId:
                    type: string
                    example: "RumwQpBaDctlUu5jyG5rs0"
                  transactionTime:
                    type: integer
                    format: int64
                    example: 1712291372842
                  symbol:
                    type: string
                    example: "LTCBTC"
                  orders:
                    type: array
                    items:
                      type: object
                      properties:
                        symbol:
                          type: string
                        orderId:
                          type: integer
                          format: int64
                        clientOrderId:
                          type: string
                      required:
                        - symbol
                        - orderId
                        - clientOrderId
                      example:
                        - symbol: "LTCBTC"
                          orderId: 6
                          clientOrderId: "fM9Y4m23IFJVCQmIrlUmMK"
                        - symbol: "LTCBTC"
                          orderId: 7
                          clientOrderId: "6pcQbFIzTXGZQ1e2MkGDq4"
                        - symbol: "LTCBTC"
                          orderId: 8
                          clientOrderId: "r4JMv9cwAYYUwwBZfbussx"
                  orderReports:
                    type: array
                    items:
                      type: object
                      properties:
                        symbol:
                          type: string
                        orderId:
                          type: integer
                          format: int64
                        orderListId:
                          type: integer
                          format: int64
                        clientOrderId:
                          type: string
                        transactTime:
                          type: integer
                          format: int64
                        price:
                          type: string
                        origQty:
                          type: string
                        executedQty:
                          type: string
                        cummulativeQuoteQty:
                          type: string
                        status:
                          type: string
                        timeInForce:
                          type: string
                        type:
                          type: string
                        side:
                          type: string
                        workingTime:
                          type: integer
                          format: int64
                        selfTradePreventionMode:
                          type: string
                      required:
                        - symbol
                        - orderId
                        - orderListId
                        - clientOrderId
                        - transactTime
                        - price
                        - origQty
                        - executedQty
                        - cummulativeQuoteQty
                        - status
                        - timeInForce
                        - type
                        - side
                        - workingTime
                        - selfTradePreventionMode
                      example:
                        - symbol: "LTCBTC"
                          orderId: 6
                          orderListId: 1
                          clientOrderId: "fM9Y4m23IFJVCQmIrlUmMK"
                          transactTime: 1712291372842
                          price: "1.000000"
                          origQty: "1.00000000"
                          executedQty: "0.00000000"
                          cummulativeQuoteQty: "0.00000000"
                          status: "NEW"
                          timeInForce: "GTC"
                          type: "LIMIT"
                          side: "SELL"
                          workingTime: 1712291372842
                          selfTradePreventionMode: "NONE"
                        - symbol: "LTCBTC"
                          orderId: 7
                          orderListId: 1
                          clientOrderId: "6pcQbFIzTXGZQ1e2MkGDq4"
                          transactTime: 1712291372842
                          price: "1.00000000"
                          origQty: "5.00000000"
                          executedQty: "0.00000000"
                          cummulativeQuoteQty: "0.00000000"
                          status: "PENDING_NEW"
                          timeInForce: "IOC"
                          type: "STOP_LOSS_LIMIT"
                          side: "BUY"
                          stopPrice: "6.00000000"
                          workingTime: -1
                          selfTradePreventionMode: "NONE"
                        - symbol: "LTCBTC"
                          orderId: 8
                          orderListId: 1
                          clientOrderId: "r4JMv9cwAYYUwwBZfbussx"
                          transactTime: 1712291372842
                          price: "3.00000000"
                          origQty: "5.00000000"
                          executedQty: "0.00000000"
                          cummulativeQuoteQty: "0.00000000"
                          status: "PENDING_NEW"
                          timeInForce: "GTC"
                          type: "LIMIT_MAKER"
                          side: "BUY"
                          workingTime: -1
                          selfTradePreventionMode: "NONE"
                required:
                  - orderListId
                  - contingencyType
                  - listStatusType
                  - listOrderStatus
                  - listClientOrderId
                  - transactionTime
                  - symbol
                  - orders
                  - orderReports
        '400':
          description: Bad Request
          content:
            application/json:
              schema:
                $ref: '#/components/schemas/error'
        '401':
            description: Unauthorized Request
            content:
              application/json:
                schema:
                  $ref: '#/components/schemas/error'
  /api/v3/orderList:
    get:
      summary: Query OCO (USER_DATA)
      description: |-
        Retrieves a specific OCO based on provided optional parameters

        Weight(IP): 4
      tags:
        - Trade
      parameters:
        - $ref: '#/components/parameters/orderListId'
        - $ref: '#/components/parameters/origClientOrderId'
        - $ref: '#/components/parameters/recvWindow'
        - $ref: '#/components/parameters/timestamp'
        - $ref: '#/components/parameters/signature'
      security:
        - ApiKeyAuth: []
      responses:
        '200':
          description: OCO details
          content:
            application/json:
              schema:
                type: object
                properties:
                  orderListId:
                    type: integer
                    format: int64
                    example: 27
                  contingencyType:
                    type: string
                    example: "OCO"
                  listStatusType:
                    type: string
                    example: "EXEC_STARTED"
                  listOrderStatus:
                    type: string
                    example: "EXECUTING"
                  listClientOrderId:
                    type: string
                    example: "h2USkA5YQpaXHPIrkd96xE"
                  transactionTime:
                    type: integer
                    format: int64
                    example: 1565245656253
                  symbol:
                    type: string
                    example: "LTCBTC"
                  orders:
                    type: array
                    items:
                      type: object
                      properties:
                        symbol:
                          type: string
                        orderId:
                          type: integer
                          format: int64
                        clientOrderId:
                          type: string
                      example:
                        - symbol: "LTCBTC"
                          orderId: 4
                          clientOrderId: "qD1gy3kc3Gx0rihm9Y3xwS"
                        - symbol: "LTCBTC"
                          orderId: 5
                          clientOrderId: "ARzZ9I00CPM8i3NhmU9Ega"
                      required:
                        - symbol
                        - orderId
                        - clientOrderId
                required:
                  - orderListId
                  - contingencyType
                  - listStatusType
                  - listOrderStatus
                  - listClientOrderId
                  - transactionTime
                  - symbol
                  - orders
        '400':
          description: Bad Request
          content:
            application/json:
              schema:
                $ref: '#/components/schemas/error'
        '401':
            description: Unauthorized Request
            content:
              application/json:
                schema:
                  $ref: '#/components/schemas/error'
    delete:
      summary: Cancel OCO (TRADE)
      description: |-
        Cancel an entire Order List

        Canceling an individual leg will cancel the entire OCO

        Weight(IP): 1
      tags:
        - Trade
      parameters:
        - $ref: '#/components/parameters/symbol'
        - $ref: '#/components/parameters/orderListId'
        - $ref: '#/components/parameters/listClientOrderId'
        - $ref: '#/components/parameters/newClientOrderId'
        - $ref: '#/components/parameters/recvWindow'
        - $ref: '#/components/parameters/timestamp'
        - $ref: '#/components/parameters/signature'
      security:
        - ApiKeyAuth: []
      responses:
        '200':
          description: Report on deleted OCO
          content:
            application/json:
              schema:
                $ref: '#/components/schemas/ocoOrder'
        '400':
          description: Bad Request
          content:
            application/json:
              schema:
                $ref: '#/components/schemas/error'
        '401':
            description: Unauthorized Request
            content:
              application/json:
                schema:
                  $ref: '#/components/schemas/error'
  /api/v3/allOrderList:
    get:
      summary: Query all OCO (USER_DATA)
      description: |-
        Retrieves all OCO based on provided optional parameters

        Weight(IP): 20
      tags:
        - Trade
      parameters:
        - $ref: '#/components/parameters/fromId'
        - $ref: '#/components/parameters/startTime'
        - $ref: '#/components/parameters/endTime'
        - $ref: '#/components/parameters/limit'
        - $ref: '#/components/parameters/recvWindow'
        - $ref: '#/components/parameters/timestamp'
        - $ref: '#/components/parameters/signature'
      security:
        - ApiKeyAuth: []
      responses:
        '200':
          description: List of OCO orders
          content:
            application/json:
              schema:
                type: array
                items:
                  type: object
                  properties:
                    orderListId:
                      type: integer
                      format: int64
                      example: 29
                    contingencyType:
                      type: string
                      example: "OCO"
                    listStatusType:
                      type: string
                      example: "EXEC_STARTED"
                    listOrderStatus:
                      type: string
                      example: "EXECUTING"
                    listClientOrderId:
                      type: string
                      example: "amEEAXryFzFwYF1FeRpUoZ"
                    transactionTime:
                      type: integer
                      format: int64
                      example: 1565245913483
                    symbol:
                      type: string
                      example: "LTCBTC"
                    isIsolated:
                      type: boolean
                    orders:
                      type: array
                      items:
                        type: object
                        properties:
                          symbol:
                            type: string
                          orderId:
                            type: integer
                            format: int64
                          clientOrderId:
                            type: string
                        example:
                          - symbol: "LTCBTC"
                            orderId: 4
                            clientOrderId: "oD7aesZqjEGlZrbtRpy5zB"
                          - symbol: "LTCBTC"
                            orderId: 5
                            clientOrderId: "Jr1h6xirOxgeJOUuYQS7V3"
                        required:
                          - symbol
                          - orderId
                          - clientOrderId
                  required:
                    - orderListId
                    - contingencyType
                    - listStatusType
                    - listOrderStatus
                    - listClientOrderId
                    - transactionTime
                    - symbol
                    - isIsolated
                    - orders
        '400':
          description: Bad Request
          content:
            application/json:
              schema:
                $ref: '#/components/schemas/error'
        '401':
            description: Unauthorized Request
            content:
              application/json:
                schema:
                  $ref: '#/components/schemas/error'
  /api/v3/openOrderList:
    get:
      summary: Query Open OCO (USER_DATA)
      description: 'Weight(IP): 6'
      tags:
        - Trade
      parameters:
        - $ref: '#/components/parameters/recvWindow'
        - $ref: '#/components/parameters/timestamp'
        - $ref: '#/components/parameters/signature'
      security:
        - ApiKeyAuth: []
      responses:
        '200':
          description: List of OCO orders
          content:
            application/json:
              schema:
                type: array
                items:
                  type: object
                  properties:
                    orderListId:
                      type: integer
                      format: int64
                      example: 31
                    contingencyType:
                      type: string
                      example: "OCO"
                    listStatusType:
                      type: string
                      example: "EXEC_STARTED"
                    listOrderStatus:
                      type: string
                      example: "EXECUTING"
                    listClientOrderId:
                      type: string
                      example: "wuB13fmulKj3YjdqWEcsnp"
                    transactionTime:
                      type: integer
                      format: int64
                      example: 1565246080644
                    symbol:
                      type: string
                      example: "LTCBTC"
                    orders:
                      type: array
                      items:
                        type: object
                        properties:
                          symbol:
                            type: string
                          orderId:
                            type: integer
                            format: int64
                          clientOrderId:
                            type: string
                        required:
                          - symbol
                          - orderId
                          - clientOrderId
                        example:
                          - symbol: "LTCBTC"
                            orderId: 4
                            clientOrderId: "r3EH2N76dHfLoSZWIUw1bT"
                          - symbol: "LTCBTC"
                            orderId: 5
                            clientOrderId: "Cv1SnyPD3qhqpbjpYEHbd2"
                  required:
                    - orderListId
                    - contingencyType
                    - listStatusType
                    - listOrderStatus
                    - listClientOrderId
                    - transactionTime
                    - symbol
                    - orders
        '400':
          description: Bad Request
          content:
            application/json:
              schema:
                $ref: '#/components/schemas/error'
        '401':
            description: Unauthorized Request
            content:
              application/json:
                schema:
                  $ref: '#/components/schemas/error'
  /api/v3/sor/order:
    post:
      summary: New order using SOR (TRADE)
      description: 'Weight(IP): 6'
      tags:
        - Trade
      parameters:
        - $ref: '#/components/parameters/symbol'
        - $ref: '#/components/parameters/side'
        - $ref: '#/components/parameters/orderType'
        - $ref: '#/components/parameters/timeInForce'
        - $ref: '#/components/parameters/quantity'
        - name: price
          in: query
          required: false
          schema:
            type: number
            format: double
        - $ref: '#/components/parameters/newClientOrderId'
        - $ref: '#/components/parameters/strategyId'
        - $ref: '#/components/parameters/strategyType'
        - $ref: '#/components/parameters/icebergQty'
        - $ref: '#/components/parameters/newOrderRespType'
        - $ref: '#/components/parameters/selfTradePreventionMode'
        - $ref: '#/components/parameters/recvWindow'
        - $ref: '#/components/parameters/timestamp'
        - $ref: '#/components/parameters/signature'
      security:
        - ApiKeyAuth: []
      responses:
        '200':
          description: New order details
          content:
            application/json:
              schema:
                type: object
                properties:
                  symbol:
                    type: string
                    example: "BTCUSDT"
                  orderId:
                    type: integer
                    format: int64
                    example: 2
                  orderListId:
                    type: integer
                    format: int64
                    example: -1
                  clientOrderId:
                    type: string
                    example: "sBI1KM6nNtOfj5tccZSKly"
                  transactTime:
                    type: integer
                    format: int64
                    example: 1689149087774
                  price:
                    type: string
                    example: "31000.00000000"
                  origQty:
                    type: string
                    example: "0.50000000"
                  executedQty:
                    type: string
                    example: "0.50000000"
                  cummulativeQuoteQty:
                    type: string
                    example: "14000.00000000"
                  status:
                    type: string
                    example: "FILLED"
                  timeInForce:
                    type: string
                    example: "GTC"
                  type:
                    type: string
                    example: "LIMIT"
                  side:
                    type: string
                    example: "BUY"
                  workingTime:
                    type: integer
                    format: int64
                    example: 1689149087774
                  fills:
                    type: array
                    items:
                      type: object
                      properties:
                        matchType:
                          type: string
                          example: "ONE_PARTY_TRADE_REPORT"
                        price:
                          type: string
                          example: "28000.00000000"
                        qty:
                          type: string
                          example: "0.50000000"
                        commission:
                          type: string
                          example: "0.00000000"
                        commissionAsset:
                          type: string
                          example: "BTC"
                        tradeId:
                          type: integer
                          format: int64
                          example: -1
                        allocId:
                          type: integer
                          format: int64
                          example: 0
                      required:
                        - matchType
                        - price
                        - qty
                        - commission
                        - commissionAsset
                        - tradeId
                        - allocId
                  workingFloor:
                    type: string
                    example: "SOR"
                  selfTradePreventionMode:
                    type: string
                    example: "NONE"
                  usedSor:
                    type: boolean
                    example: true
                required:
                  - symbol
                  - orderId
                  - orderListId
                  - clientOrderId
                  - transactTime
                  - price
                  - origQty
                  - executedQty
                  - cummulativeQuoteQty
                  - status
                  - timeInForce
                  - type
                  - side
                  - workingTime
                  - fills
                  - workingFloor
                  - selfTradePreventionMode
                  - usedSor
        '400':
          description: Bad Request
          content:
            application/json:
              schema:
                $ref: '#/components/schemas/error'
        '401':
          description: Unauthorized Request
          content:
            application/json:
              schema:
                $ref: '#/components/schemas/error'
  /api/v3/sor/order/test:
    post:
      summary: Test new order using SOR (TRADE)
      description: |-
        Test new order creation and signature/recvWindow using smart order routing (SOR).
        Creates and validates a new order but does not send it into the matching engine.

        Weight(IP):
          - Without computeCommissionRates: `1`
          - With computeCommissionRates: `20`
      tags:
        - Trade
      parameters:
        - $ref: '#/components/parameters/symbol'
        - $ref: '#/components/parameters/side'
        - $ref: '#/components/parameters/orderType'
        - $ref: '#/components/parameters/timeInForce'
        - $ref: '#/components/parameters/quantity'
        - name: price
          in: query
          required: false
          schema:
            type: number
            format: double
        - $ref: '#/components/parameters/newClientOrderId'
        - $ref: '#/components/parameters/strategyId'
        - $ref: '#/components/parameters/strategyType'
        - $ref: '#/components/parameters/icebergQty'
        - $ref: '#/components/parameters/newOrderRespType'
        - $ref: '#/components/parameters/selfTradePreventionMode'
        - name: computeCommissionRates
          in: query
          required: false
          description: |-
            Default: false
          schema:
            type: boolean
            example: false
        - $ref: '#/components/parameters/recvWindow'
        - $ref: '#/components/parameters/timestamp'
        - $ref: '#/components/parameters/signature'
      security:
        - ApiKeyAuth: []
      responses:
        '200':
          description: Test new order
          content:
            application/json:
              schema:
                type: object
        '400':
          description: Bad Request
          content:
            application/json:
              schema:
                $ref: '#/components/schemas/error'
        '401':
          description: Unauthorized Request
          content:
            application/json:
              schema:
                $ref: '#/components/schemas/error'
  /api/v3/account:
    get:
      summary: Account Information (USER_DATA)
      description: |-
        Get current account information.

        Weight(IP): 20
      tags:
        - Trade
      parameters:
        - $ref: '#/components/parameters/recvWindow'
        - $ref: '#/components/parameters/timestamp'
        - $ref: '#/components/parameters/signature'
      security:
        - ApiKeyAuth: []
      responses:
        '200':
          description: Account details
          content:
            application/json:
              schema:
                $ref: '#/components/schemas/account'
        '400':
          description: Bad Request
          content:
            application/json:
              schema:
                $ref: '#/components/schemas/error'
        '401':
            description: Unauthorized Request
            content:
              application/json:
                schema:
                  $ref: '#/components/schemas/error'
  /api/v3/myTrades:
    get:
      summary: Account Trade List (USER_DATA)
      description: |-
        Get trades for a specific account and symbol.

        If `fromId` is set, it will get id >= that `fromId`. Otherwise most recent orders are returned.

        The time between startTime and endTime can't be longer than 24 hours.
        These are the supported combinations of all parameters:

          symbol

          symbol + orderId

          symbol + startTime

          symbol + endTime

          symbol + fromId

          symbol + startTime + endTime

          symbol+ orderId + fromId

        Weight(IP): 20
      tags:
        - Trade
      parameters:
        - $ref: '#/components/parameters/symbol'
        - name: orderId
          in: query
          description: This can only be used in combination with symbol.
          schema:
            type: integer
            format: int64
        - $ref: '#/components/parameters/startTime'
        - $ref: '#/components/parameters/endTime'
        - $ref: '#/components/parameters/fromId'
        - $ref: '#/components/parameters/limit'
        - $ref: '#/components/parameters/recvWindow'
        - $ref: '#/components/parameters/timestamp'
        - $ref: '#/components/parameters/signature'
      security:
        - ApiKeyAuth: []
      responses:
        '200':
          description: List of trades
          content:
            application/json:
              schema:
                type: array
                items:
                  $ref: '#/components/schemas/myTrade'
        '400':
          description: Bad Request
          content:
            application/json:
              schema:
                $ref: '#/components/schemas/error'
        '401':
            description: Unauthorized Request
            content:
              application/json:
                schema:
                  $ref: '#/components/schemas/error'
  /api/v3/rateLimit/order:
    get:
      summary: Query Current Order Count Usage (TRADE)
      description: |-
        Displays the user's current order count usage for all intervals.

        Weight(IP): 40
      tags:
        - Trade
      parameters:
        - $ref: '#/components/parameters/recvWindow'
        - $ref: '#/components/parameters/timestamp'
        - $ref: '#/components/parameters/signature'
      security:
        - ApiKeyAuth: []
      responses:
        '200':
          description: Order rate limits
          content:
            application/json:
              schema:
                type: array
                items:
                  type: object
                  properties:
                    rateLimitType:
                      type: string
                    interval:
                      type: string
                    intervalNum:
                      type: integer
                      format: int32
                    limit:
                      type: integer
                      format: int32
                    count:
                      type: integer
                      format: int32
                  required:
                    - rateLimitType
                    - interval
                    - intervalNum
                    - limit
                example:
                  - rateLimitType: "ORDERS"
                    interval: "SECOND"
                    intervalNum: 10
                    limit: 10000
                    count: 0
                  - rateLimitType: "ORDERS"
                    interval: "DAY"
                    intervalNum: 1
                    limit: 20000
                    count: 0
        '400':
          description: Bad Request
          content:
            application/json:
              schema:
                $ref: '#/components/schemas/error'
        '401':
            description: Unauthorized Request
            content:
              application/json:
                schema:
                  $ref: '#/components/schemas/error'
  /api/v3/myPreventedMatches:
    get:
      summary: Query Prevented Matches
      description: |-
        Displays the list of orders that were expired because of STP.

        For additional information on what a Prevented match is, as well as Self Trade Prevention (STP), please refer to our STP FAQ page.

        These are the combinations supported:

        * symbol + preventedMatchId
        * symbol + orderId
        * symbol + orderId + fromPreventedMatchId (limit will default to 500)
        * symbol + orderId + fromPreventedMatchId + limit

        Weight(IP):

        Case 	                          Weight
        If symbol is invalid: 	        2
        Querying by preventedMatchId: 	2
        Querying by orderId: 	          20

      tags:
        - Trade
      parameters:
        - $ref: '#/components/parameters/symbol'
        - $ref: '#/components/parameters/preventedMatchId'
        - $ref: '#/components/parameters/orderId'
        - name: fromPreventedMatchId
          in: query
          required: false
          schema:
            type: integer
            format: int64
            example: 1
        - $ref: '#/components/parameters/limit'
        - $ref: '#/components/parameters/recvWindow'
        - $ref: '#/components/parameters/timestamp'
        - $ref: '#/components/parameters/signature'
      security:
        - ApiKeyAuth: []
      responses:
        '200':
          description: Order list that were expired due to STP
          content:
            application/json:
              schema:
                type: array
                items:
                  type: object
                  properties:
                    symbol:
                      type: string
                      example: "BTCUSDT"
                    preventedMatchId:
                      type: integer
                      format: int64
                      example: 1
                    takerOrderId:
                      type: integer
                      format: int64
                      example: 5
                    makerOrderId:
                      type: integer
                      format: int64
                      example: 3
                    tradeGroupId:
                      type: integer
                      format: int64
                      example: 1
                    selfTradePreventionMode:
                      type: string
                      example: "EXPIRE_MAKER"
                    price:
                      type: string
                      example: "1.100000"
                    makerPreventedQuantity:
                      type: string
                      example: "1.300000"
                    transactTime:
                      type: integer
                      format: int64
                      example: 1669101687094
                  required:
                    - symbol
                    - preventedMatchId
                    - takerOrderId
                    - makerOrderId
                    - tradeGroupId
                    - selfTradePreventionMode
                    - price
                    - makerPreventedQuantity
                    - transactTime
        '400':
          description: Bad Request
          content:
            application/json:
              schema:
                $ref: '#/components/schemas/error'
        '401':
            description: Unauthorized Request
            content:
              application/json:
                schema:
                  $ref: '#/components/schemas/error'
  /api/v3/myAllocations:
    get:
      summary: Query Allocations (USER_DATA)
      description: |-
        Retrieves allocations resulting from SOR order placement.

        Weight: 20

        Supported parameter combinations:
        Parameters 	                          Response
        symbol 	                              allocations from oldest to newest
        symbol + startTime 	                  oldest allocations since startTime
        symbol + endTime 	                    newest allocations until endTime
        symbol + startTime + endTime 	        allocations within the time range
        symbol + fromAllocationId 	          allocations by allocation ID
        symbol + orderId 	                    allocations related to an order starting with oldest
        symbol + orderId + fromAllocationId 	allocations related to an order by allocation ID

        Note: The time between startTime and endTime can't be longer than 24 hours.
      tags:
        - Trade
      parameters:
        - $ref: '#/components/parameters/symbol'
        - $ref: '#/components/parameters/startTime'
        - $ref: '#/components/parameters/endTime'
        - name: fromAllocationId
          in: query
          required: false
          schema:
            type: integer
            format: int64
        - $ref: '#/components/parameters/limit'
        - $ref: '#/components/parameters/orderId'
        - $ref: '#/components/parameters/recvWindow'
        - $ref: '#/components/parameters/timestamp'
        - $ref: '#/components/parameters/signature'
      security:
        - ApiKeyAuth: []
      responses:
        '200':
          description: Allocations resulting from SOR order placement
          content:
            application/json:
              schema:
                type: array
                items:
                  type: object
                  properties:
                    symbol:
                      type: string
                      example: "BTCUSDT"
                    allocationId:
                      type: integer
                      format: int64
                      example: 0
                    allocationType:
                      type: string
                      example: "SOR"
                    orderId:
                      type: integer
                      format: int64
                      example: 1
                    orderListId:
                      type: integer
                      format: int64
                      example:  -1
                    price:
                      type: string
                      example: "1.00000000"
                    qty:
                      type: string
                      example: "5.00000000"
                    quoteQty:
                      type: string
                      example: "5.00000000"
                    commission:
                      type: string
                      example: "0.00000000"
                    commissionAsset:
                      type: string
                      example: "BTC"
                    time:
                      type: integer
                      format: int64
                      example: 1687506878118
                    isBuyer:
                      type: boolean
                      example: true
                    isMaker:
                      type: boolean
                      example: false
                    isAllocator:
                      type: boolean
                      example: false
                  required:
                    - symbol
                    - allocationId
                    - allocationType
                    - orderId
                    - orderListId
                    - price
                    - qty
                    - quoteQty
                    - commission
                    - commissionAsset
                    - time
                    - isBuyer
                    - isMaker
                    - isAllocator
        '400':
          description: Bad Request
          content:
            application/json:
              schema:
                $ref: '#/components/schemas/error'
        '401':
            description: Unauthorized Request
            content:
              application/json:
                schema:
                  $ref: '#/components/schemas/error'
  /api/v3/account/commission:
    get:
      summary: Query Commission Rates (USER_DATA)
      description: |-
        Get current account commission rates.

        Weight: 20
      tags:
        - Trade
      parameters:
        - $ref: '#/components/parameters/symbol'
        - $ref: '#/components/parameters/timestamp'
        - $ref: '#/components/parameters/signature'
      security:
        - ApiKeyAuth: []
      responses:
        '200':
          description: Current account commission rates.
          content:
            application/json:
              schema:
                type: object
                properties:
                  symbol:
                    type: string
                    example: "BTCUSDT"
                  standardCommission:
                    type: object
                    description: Standard commission rates on trades from the order.
                    properties:
                      maker:
                        type: string
                        example: "0.00000010"
                      taker:
                        type: string
                        example: "0.00000020"
                      buyer:
                        type: string
                        example: "0.00000030"
                      seller:
                        type: string
                        example: "0.00000040"
                    required:
                      - maker
                      - taker
                      - buyer
                      - seller
                  taxCommission:
                    type: object
                    description: Tax commission rates for trades from the order.
                    properties:
                      maker:
                        type: string
                        example: "0.00000112"
                      taker:
                        type: string
                        example: "0.00000114"
                      buyer:
                        type: string
                        example: "0.00000118"
                      seller:
                        type: string
                        example: "0.00000116"
                    required:
                      - maker
                      - taker
                      - buyer
                      - seller
                  discount:
                    type: object
                    description: Discount commission when paying in BNB.
                    properties:
                      enabledForAccount:
                        type: boolean
                        example: true
                      enabledForSymbol:
                        type: boolean
                        example: true
                      discountAsset:
                        type: string
                        example: "BNB"
                      discount:
                        type: string
                        description: Standard commission is reduced by this rate when paying commission in BNB.
                        example: "0.25000000"
                required:
                  - symbol
                  - standardCommission
                  - taxCommission
                  - discount
        '400':
          description: Bad Request
          content:
            application/json:
              schema:
                $ref: '#/components/schemas/error'
        '401':
            description: Unauthorized Request
            content:
              application/json:
                schema:
                  $ref: '#/components/schemas/error'

 