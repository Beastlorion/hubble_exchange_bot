import time, ast, asyncio
import urllib.request
from binance import AsyncClient, BinanceSocketManager
import tools

api_key = ''
api_secret = ''
usdt = 0
priceUSD = 0

def startPriceFeed(market):
  usdtUpdaterTask = asyncio.create_task(usdtUpdater())
  tickerTask = asyncio.create_task(startTicker(market))
  
async def usdtUpdater():
  while 1:
    await updateUSDT()
    await asyncio.sleep(1)

async def startTicker(market):
  symbol = tools.getSymbolFromName(market) + 'USDT'

  client = await AsyncClient.create()
  bm = BinanceSocketManager(client)
  # start any sockets here, i.e a trade socket
  ts = bm.trade_socket(symbol)
  # then start receiving messages
  async with ts as tscm:
    while True:
      res = await tscm.recv()
      priceUsdt = float(res["p"])
      if usdt:
        global priceUSD
        priceUSD = priceUsdt * usdt
        # print("USD PRICE:",priceUSD)
  await client.close_connection()

async def updateUSDT():
  try:
    usdtResult = urllib.request.urlopen("https://api.kraken.com/0/public/Ticker?pair=USDTUSD").read()
    usdtResult = ast.literal_eval(usdtResult.decode('utf-8')) 
    global usdt
    usdt = (float(usdtResult["result"]["USDTZUSD"]["a"][0]) + float(usdtResult["result"]["USDTZUSD"]["b"][0]))/2;
  except:
    print("error getting usdt price")


# def getTickerPrice():
