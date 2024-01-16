import sys, os, asyncio, time
from decimal import *
from hexbytes import HexBytes
from hubble_exchange import HubbleClient, OrderBookDepthResponse, LimitOrder, IOCOrder
from hubble_exchange.constants import get_minimum_quantity, get_price_precision
from dotenv import load_dotenv, dotenv_values
import tools
import price_feeds

async def orderUpdater(client,marketID,settings):
  lastUpdatePrice = 0
  
  while True:
    midPrice = tools.getMidPrice("0")
    if midPrice == 0:
      await asyncio.sleep(2)
      continue
    if abs(lastUpdatePrice - midPrice)/midPrice > float(settings["refreshTolerance"])/100:
      
      nonce = await client.get_nonce() # refresh nonce
      try: 
        await cancelAllOrders(client,marketID)
      except:
        continue
      positions = await client.get_margin_and_positions(tools.callback)
      thisPosition = {}
      for position in positions.positions:
        if position["market"] == marketID:
          thisPosition = position
      availableMargin = float(positions.margin) * float(settings["marginShare"])
      availableMarginBid = availableMargin
      availableMarginAsk = availableMargin
      multiple = 0
      defensiveSkewBid = 0
      defensiveSkewAsk = 0
      if (len(thisPosition) > 0 and float(thisPosition["size"]) > 0):
        availableMarginBid = availableMargin - (float(thisPosition["notionalPosition"])/float(settings["leverage"]))
        multiple = (float(thisPosition["notionalPosition"])/float(settings["leverage"]))/availableMargin
        defensiveSkewBid = multiple * 10 * settings["defensiveSkew"]/100;
      elif (len(thisPosition)>0 and float(thisPosition["size"]) < 0):
        availableMarginAsk = availableMargin - (float(thisPosition["notionalPosition"])/float(settings["leverage"]))
        multiple = (float(thisPosition["notionalPosition"])/float(settings["leverage"]))/availableMargin
        defensiveSkewAsk = multiple * 10 * settings["defensiveSkew"]/100;
      print("availableMarginBid: ",availableMarginBid, "  availableMarginAsk: ",availableMarginAsk, multiple)
      
      buyOrders = generateBuyOrders(marketID,midPrice,settings,availableMarginBid,defensiveSkewBid)
      sellOrders = generateSellOrders(marketID,midPrice,settings,availableMarginAsk,defensiveSkewAsk)
      
      limit_orders = []
      limit_orders = buyOrders + sellOrders
      
      if len(limit_orders) > 0:
        try:
          placed_orders = await client.place_limit_orders(limit_orders, True, tools.placeOrdersCallback)
          lastUpdatePrice = midPrice
          await asyncio.sleep(settings["refreshInterval"])
          continue
        except Exception as error:
          print("failed to place orders",error)
          continue
    await asyncio.sleep(1)
      

  
  # fundingRate = await client.get_funding_rate(marketID,time.time())
  # fundingRate = fundingRate["fundingRate"]
  # print("last funding rate:", fundingRate)
  
  # nextFundingRate = await client.get_predicted_funding_rate(marketID)
  # nextFundingRate = nextFundingRate["fundingRate"]
  # print("next funding rate:",nextFundingRate)
  
def generateBuyOrders(marketID, midPrice, settings, availableMargin, defensiveSkew):
  orders = []
  leverage = float(settings["leverage"])
  for level in settings["orderLevels"]:
    l = settings["orderLevels"][level]
    spread = float(l["spread"])/100 + defensiveSkew
    bidPrice = midPrice * (1 - spread)
    roundedBidPrice = round(bidPrice,get_price_precision(marketID))
    
    amtToTrade = (availableMargin * leverage)/roundedBidPrice
    qty = getQty(l,amtToTrade,marketID)
    if qty == 0:
      continue
    availableMargin = availableMargin - ((qty * roundedBidPrice)/leverage)
    order = LimitOrder.new(marketID,qty,roundedBidPrice,False,True)
    orders.append(order)
  return orders
  
def generateSellOrders(marketID, midPrice, settings, availableMargin, defensiveSkew):
  orders = []
  leverage = float(settings["leverage"])
  for level in settings["orderLevels"]:
    l = settings["orderLevels"][level]
    spread = float(l["spread"])/100 + defensiveSkew
    askPrice = midPrice * (1 + spread)
    roundedAskPrice = round(askPrice,get_price_precision(marketID))
    amtToTrade = (availableMargin * leverage)/roundedAskPrice
    qty = getQty(l,amtToTrade,marketID) * -1
    if qty == 0:
      continue
    availableMargin = availableMargin - ((qty * roundedAskPrice)/leverage)
    order = LimitOrder.new(marketID,qty,roundedAskPrice,False,True)
    orders.append(order)
  return orders

async def cancelAllOrders(client, marketID):
  open_orders = await client.get_open_orders(marketID, tools.callback)
  tasks = []
  if len(open_orders)>0:
    for order in open_orders:
      tasks.append(client.cancel_order_by_id(HexBytes(order.OrderId), True, tools.placeOrdersCallback))
  await asyncio.gather(*tasks)
  return
      
def getQty(level, amtToTrade,marketID):
  if float(level["qty"]) < amtToTrade:
    return float(level["qty"])
  elif amtToTrade > get_minimum_quantity(marketID):
    return float(Decimal(amtToTrade).quantize(Decimal(get_minimum_quantity(marketID)), rounding=ROUND_DOWN))
  else:
    return 0