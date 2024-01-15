# Beastlorion's Dexalot MarketMaker

## Setup

Assuming you are using a fresh server:

```
pip install hubble-exchange
pip install python-binance
vi .env.secret
i
```

paste this with your private key:

```
export PRIVATE_KEY=""
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

Check the settings for each market in .env.shared and adjust them to your liking. The spreads are in %. So "spread":0.1 = 0.1%

## Run
Run with your market of choice: AVAX, ETH, or SOL
```
python3 main.py AVAX
```
To stop press ctr+c
It may be necessary to press multiple times

## Flow

1. Starts Binance price feed for asset/usdt
2. Begins loop to get usdt/usd price from kraken
3. Starts orderUpdater loop:
  - Fetches all open orders for the market and cancels them
  - Calculates prices and quantities for orders
  - Places orders
  - waits 5 seconds if successful. If unsuccessful try again faster
4. On shutdown cancels all open orders for the market