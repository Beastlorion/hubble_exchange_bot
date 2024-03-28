# Beastlorion's Hubble Market Maker Bot

## Setup

```
git clone https://github.com/hubble-exchange/beast_mm_bot

cd beast_mm_bot

```


# You will need python 3.10 to run the bot

# Step 1 - install virtualenv if not already installed. This only needs to be done for the first time
```sudo apt install python3-env```

# Step 2 - create a new virtual environment. 
```python3.10 -m venv venv && source venv/bin/activate```

# Step 3 - To install the dependencies, use the following terminal commands, ignore any errors shown for dependency package mismatch in SDKs 

```
pip install -r setuptools pandas numpy cachetools hubble_exchange==0.9.0rc10 python-binance python-dotenv git+https://github.com/shubhamgoyal42/aio-binance-library 
pip install hyperliquid-python-sdk==0.1.19
pip uninstall eth-account
pip install eth-account==0.10.0
```

## Add your Credentials for managing Hubble, Binance and Hyperliquid accounts
`vi .env.secret`

paste this with your private key/keys:

```
export AVAX_PRIVATE_KEY=""
export ETH_PRIVATE_KEY=""
export SOL_PRIVATE_KEY=""
export HYPERLIQUID_TRADER=""
export HYPERLIQUID_PRIVATE_KEY=""
export BINANCE_API_KEY=""
export BINANCE_SECRET_KEY=""
```
Then press :wq to write the file and exit the editor


You may also need to add the python packages in your .bashrc file: 

```
vi ~/.bashrc
i
```

paste this in on the last line and then type :wq to save an quit
```
export PATH="/.local/bin:$PATH"
```

Check the settings for each market in .config.py and adjust them to your liking. The spreads are in %. So "spread":0.1 = 0.1%

## Run
Run with your market of choice: AVAX, ETH, or SOL
```
python3 main.py AVAX
```
To stop press ctr+c
It may be necessary to press multiple times


## Run using PM2

```
sudo apt install nodejs
sudo apt install npm
sudo npm install pm2@latest -g
```


```
pm2 start ecosystem.config.js --only avax
```


## Flow

1. Start Mid Price feed from configured source (binance_futures/binance_spot) at settings.futures_feed_frequency
2. If hedge mode starts hedge client (Hyperliquid or binance)
3. Start hubble orderbook feed @ settings.hubble_orderbook_frequency
    - onBreak
      - clears the hubble_price_streaming_event
      - tries reconnecting for 5 times.
        - on successful reconnect
          - set hubble_price_streaming_event
        - on failure
          - report and exit application
4. start OrderManager

### OrderManager
  Start
  - start in background an orderfill callback listener (start_order_fill_feed) which continously listenes for updates to traders account like position updates, order fills etc.
  - start in background trader position data and margin data update service (start_trader_positions_feed @ settings["hubblePositionPollInterval"])
  - start create_orders service that runs @ settings["orderFrequency"]


*start_trader_positions_feed*
  - Update traders margin and market position data
  - set update timestamp
  - On Breakdown
    - Try to reconnect.
    - Set Flag (block create_orders service)
    - On Reconnect 
      - Reset Flag(resume create_orders service)
    - Else
      - reports and exit application

*order_fill_callback*
  - Check for order direction using Order_Data cache
  - Hedge Position
    - On Success
      - update performance data
    - On Failure
      - report and exit application
    - Finally
      - Trigger order fill cooldown (blocks create_orders service)

  - stores order open price and hedge price to calculate spread pnl 
  - @todo store fee data 
  - store volume in performance

*create_orders service*
  - Wait for the following conditions to be true to start orderCreationTask
  - hedge_client_uptime_event is set 
  - mid_price_streaming_event is set 
  - hubble_price_streaming_event is set 
  - orderFillCooldown
  - check if data is stale with thresholds [ , "position_data_expiry"]
    - Binance mid_price @ settings["mid_price_expiry"]
    - Hubble position data @ settings["position_data_expiry"]
  - Find free margin 
  - Update free margin for sell and buy according to current positions data and orders placed on this tick 
    @todo -> check reserved margin data recvd from api.
    @todo add math info here.
  - update bid and ask defensive skew 
    @todo add math info here
  - Generate bid and ask orders based on orderLevels defined in settings
    - Check if order is hedgable. 
      - If not skip 
      - If is hedgable add to orders 
  - Place created orders
  - wait for 


### Hedge Client

Start
  - set market leverage to settings.leverage if no existing positions.
  - start background process to fetch orderbook data @ settings.hedgeClient_orderbook_frequency
    - If this breaks
      - retries connecting for 5 times.
        - On Successful connection restore
          - Sets uptime_event
        - Else 
          - report and exit application
  - start background process to fetch user state data @ settings.hedgeClient_user_state_frequency
    - If this breaks
      - retries connecting for 5 times.
        - On Successful connection restore
          - Sets uptime_event
        - Else 
          - report and exit application
