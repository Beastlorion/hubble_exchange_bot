import price_feeds

def getKey(d,v):
  for key,item in d.items():
    if item == v:
      return key
    
def getSymbolFromName(market):
  return market.split('-')[0]

def getMidPrice(nextFundingRate):
  return price_feeds.priceUSD

async def callback(response):
  # print(f"Received response: {response}")
  return response

async def placeOrdersCallback(response):
  print(f"Received response: {response}")
  return response
