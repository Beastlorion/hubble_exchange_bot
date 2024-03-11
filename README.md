# Beastlorion's Hubble Market Maker Bot

## Setup

```
git clone https://github.com/hubble-exchange/beast_mm_bot
cd beast_mm_bot

# install virtualenv if not already installed
sudo apt install python3-env

# create a new virtual environment
python3.10 -m venv venv && source venv/bin/activate

pip install hubble-exchange==0.9.0rc6 python-binance python-dotenv

vi .env.secret
```

paste this with your private key/keys:

```
export AVAX_PRIVATE_KEY=""
export ETH_PRIVATE_KEY=""
export SOL_PRIVATE_KEY=""
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