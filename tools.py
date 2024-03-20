
def getKey(d,v):
  for key,item in d.items():
    if item == v:
      return key
    
def getSymbolFromName(market):
  return market.split('-')[0]

async def generic_callback(response):
  # print(f"Received response: {response}")
  return response
