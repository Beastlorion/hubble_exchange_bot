import sys, os, asyncio, time
from decimal import *
from hexbytes import HexBytes
from hubble_exchange import HubbleClient, OrderBookDepthResponse, LimitOrder, IOCOrder
from hubble_exchange.constants import get_minimum_quantity, get_price_precision
from dotenv import load_dotenv, dotenv_values
import tools
import price_feeds

activeOrders = []


async def orderUpdater(client, marketID, settings):
    lastUpdatePrice = 0
    nonce = await client.get_nonce()
    global activeOrders

    while True:
        midPrice = tools.getMidPrice("0")
        if midPrice == 0:
            await asyncio.sleep(2)
            continue
        if (
            abs(lastUpdatePrice - midPrice) / midPrice
            > float(settings["refreshTolerance"]) / 100
        ):

            postions = {}
            try:
                await cancelAllOrders(client, marketID)
                positions = await client.get_margin_and_positions(tools.callback)
            except Exception as error:
                print("error in cancel and get positions calls", error)
                continue
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
            if len(thisPosition) > 0 and float(thisPosition["size"]) > 0:
                availableMarginBid = availableMargin - (
                    float(thisPosition["notionalPosition"])
                    / float(settings["leverage"])
                )
                multiple = (
                    float(thisPosition["notionalPosition"])
                    / float(settings["leverage"])
                ) / availableMargin
                defensiveSkewBid = multiple * 10 * settings["defensiveSkew"] / 100
            elif len(thisPosition) > 0 and float(thisPosition["size"]) < 0:
                availableMarginAsk = availableMargin - (
                    float(thisPosition["notionalPosition"])
                    / float(settings["leverage"])
                )
                multiple = (
                    float(thisPosition["notionalPosition"])
                    / float(settings["leverage"])
                ) / availableMargin
                defensiveSkewAsk = multiple * 10 * settings["defensiveSkew"] / 100
            print(
                "availableMarginBid: ",
                availableMarginBid,
                "  availableMarginAsk: ",
                availableMarginAsk,
                multiple,
            )

            buyOrders = generateBuyOrders(
                marketID,
                midPrice,
                settings,
                availableMarginBid,
                defensiveSkewBid,
                float(thisPosition["size"]),
            )
            sellOrders = generateSellOrders(
                marketID,
                midPrice,
                settings,
                availableMarginAsk,
                defensiveSkewAsk,
                float(thisPosition["size"]),
            )

            limit_orders = []
            limit_orders = buyOrders + sellOrders

            if len(limit_orders) > 0:
                try:
                    nonce = await client.get_nonce()  # refresh nonce
                    placed_orders = await client.place_limit_orders(
                        limit_orders, True, tools.placeOrdersCallback, {"nonce": nonce}
                    )
                    # add successful orders to activeOrders tracking
                    for orderResponse in placed_orders:
                        if orderResponse["success"]:
                            for order in limit_orders:
                                if order.id == orderResponse["order_id"]:
                                    activeOrders.append(order)

                    lastUpdatePrice = midPrice
                    await asyncio.sleep(settings["refreshInterval"])
                    continue
                except Exception as error:
                    print("failed to place orders", error)
                    continue
        await asyncio.sleep(1)

    # fundingRate = await client.get_funding_rate(marketID,time.time())
    # fundingRate = fundingRate["fundingRate"]
    # print("last funding rate:", fundingRate)

    # nextFundingRate = await client.get_predicted_funding_rate(marketID)
    # nextFundingRate = nextFundingRate["fundingRate"]
    # print("next funding rate:",nextFundingRate)


def generateBuyOrders(
    marketID, midPrice, settings, availableMargin, defensiveSkew, currentSize
):
    orders = []
    amountOnOrder = 0
    leverage = float(settings["leverage"])
    for level in settings["orderLevels"]:
        l = settings["orderLevels"][level]
        spread = float(l["spread"]) / 100 + defensiveSkew
        bidPrice = midPrice * (1 - spread)
        roundedBidPrice = round(bidPrice, get_price_precision(marketID))

        amtToTrade = (availableMargin * leverage) / roundedBidPrice
        qty = getQty(l, amtToTrade, marketID)
        reduceOnly = False
        if qty == 0:
            continue
        elif currentSize < 0 and qty * -1 > currentSize + amountOnOrder:
            reduceOnly = True
            amountOnOrder = amountOnOrder + qty
        availableMargin = availableMargin - ((qty * roundedBidPrice) / leverage)
        order = LimitOrder.new(marketID, qty, roundedBidPrice, reduceOnly, True)
        orders.append(order)
    return orders


def generateSellOrders(
    marketID, midPrice, settings, availableMargin, defensiveSkew, currentSize
):
    orders = []
    amountOnOrder = 0
    leverage = float(settings["leverage"])
    for level in settings["orderLevels"]:
        l = settings["orderLevels"][level]
        spread = float(l["spread"]) / 100 + defensiveSkew
        askPrice = midPrice * (1 + spread)
        roundedAskPrice = round(askPrice, get_price_precision(marketID))
        amtToTrade = (availableMargin * leverage) / roundedAskPrice
        qty = getQty(l, amtToTrade, marketID) * -1
        reduceOnly = False
        if qty == 0:
            continue
        elif currentSize > 0 and qty * -1 < currentSize + amountOnOrder:
            reduceOnly = True
            amountOnOrder = amountOnOrder + qty
        availableMargin = availableMargin - ((qty * roundedAskPrice) / leverage)
        order = LimitOrder.new(marketID, qty, roundedAskPrice, reduceOnly, True)
        orders.append(order)
    return orders


async def cancelAllOrders(client, marketID):
    global activeOrders
    if len(activeOrders) > 0:
        try:
            nonce = await client.get_nonce()
            cancelledOrders = await client.cancel_limit_orders(
                activeOrders, True, tools.callback, {"nonce": nonce}
            )
            print("cancelledOrders", cancelledOrders)
            for orderResponse in cancelledOrders:
                if orderResponse["success"] or orderResponse["error"] == "Filled":
                    for order in activeOrders:
                        if order.id == orderResponse["order_id"]:
                            activeOrders.remove(order)
            return
        except Exception as error:
            print("there was an exception in cancel_limit_orders", error)
            return

    else:
        open_orders = await client.get_open_orders(marketID, tools.callback)
        tasks = []
        if len(open_orders) > 0:
            nonce = await client.get_nonce()  # refresh nonce
            for order in open_orders:
                tasks.append(
                    client.cancel_order_by_id(
                        HexBytes(order.OrderId), True, tools.placeOrdersCallback
                    )
                )
        await asyncio.gather(*tasks)
        return


def getQty(level, amtToTrade, marketID):
    if float(level["qty"]) < amtToTrade:
        return float(level["qty"])
    elif amtToTrade > get_minimum_quantity(marketID):
        return float(
            Decimal(str(amtToTrade)).quantize(
                Decimal(str(get_minimum_quantity(marketID))), rounding=ROUND_DOWN
            )
        )
    else:
        return 0
