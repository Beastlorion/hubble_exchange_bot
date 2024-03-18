# Beastlorion's Hubble Market Maker Bot

## Setup

```
git clone https://github.com/hubble-exchange/beast_mm_bot
cd beast_mm_bot

# You will need python 3.10 to run the bot

# Step 1 - install virtualenv if not already installed. This only needs to be done for the first time
```sudo apt install python3-env```

# Step 2 - create a new virtual environment. 
```python3.10 -m venv venv && source venv/bin/activate```

# Step 3 - To install the dependencies, use the terminal command: 
```
pip install -r requirements.txt setuptools pandas numpy cachetools hubble_exchange==0.9.0rc10 python-binance python-dotenv git+https://github.com/shubhamgoyal42/aio-binance-library hyperliquid-python-sdk==0.1.19
```

#Add your Credentials for managing Hubble, Binance and Hyperliquid accounts
vi .env.secret
```

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

1. Starts Binance price feed for asset/usdt
2. Begins loop to get usdt/usd price from kraken
3. Starts orderUpdater loop:
  - Fetches all open orders for the market and cancels them
  - Calculates prices and quantities for orders
  - Places orders
  - waits 5 seconds if successful. If unsuccessful try again
4. On shutdown cancels all open orders for the market