import sys, os, asyncio, time, ast
from hubble_exchange import HubbleClient, ConfirmationMode
from dotenv import load_dotenv, dotenv_values
import tools
import price_feeds
import marketMaker
import config
from typing import TypedDict
from hyperliquid_async import HyperLiquid
from binance_async import Binance
from hubble_exchange.models import TraderFeedUpdate
import websockets
import cachetools


env = {**dotenv_values(".env.shared"), **dotenv_values(".env.secret")}
os.environ["HUBBLE_RPC"] = env["HUBBLE_RPC"]
os.environ["HUBBLE_WS_RPC"] = env["HUBBLE_WS_RPC"]
os.environ["HUBBLE_ENV"] = env["HUBBLE_ENV"]
os.environ["PRIVATE_KEY"] = env[sys.argv[1] + "_PRIVATE_KEY"]
os.environ["HUBBLE_INDEXER_API_URL"] = env["HUBBLE_INDEXER_API_URL"]
os.environ["HYPERLIQUID_TRADER"] = env["HYPERLIQUID_TRADER"]
os.environ["HYPERLIQUID_PRIVATE_KEY"] = env["HYPERLIQUID_PRIVATE_KEY"]
# settings = ast.literal_eval(env[sys.argv[1]])
settings = getattr(config, sys.argv[1])

marketID = None

restart_needed = asyncio.Event()

async def monitor_restart():
    await restart_needed.wait()
    print("Restarting application due to a task exception.")
    # Implement your restart logic here, like exiting with a specific status code
    sys.exit(1)

hedge_client = None
hubble_client = None
active_order_direction = None

async def main(market):
    global marketID
    global hedge_client
    global hubble_client
    global active_order_direction
    hubble_client = HubbleClient(os.environ["PRIVATE_KEY"])
    expiry_duration = settings["orderExpiry"]
    active_order_direction = cachetools.TTLCache(maxsize=128, ttl=expiry_duration + 2)    monitor_task = asyncio.create_task(monitor_restart())

    try:
        if settings["priceFeed"] == "binance-futures":
            asyncio.create_task(price_feeds.start_binance_futures_feed(market, restart_needed))
        else:
            asyncio.create_task(price_feeds.start_binance_spot_feed(market))

        markets = await hubble_client.get_markets()
        marketName = settings["name"]
        assetName = marketName.split("-")[0]
        marketID = tools.getKey(markets, marketName)
        if settings["hedge"] == "hyperliquid" and settings["hedgeMode"]:
            hedge_client = HyperLiquid(
                assetName,
                {
                    "desired_max_leverage": settings["leverage"],
                    "slippage": settings["slippage"],
                },
            )
        elif settings["hedge"] == "binance" and settings["hedgeMode"]:
            hedge_client = Binance(
                assetName + "USDT",
                {
                    "desired_max_leverage": settings["leverage"],
                    "slippage": settings["slippage"],
                },
            )
        if settings["hedgeMode"]:
            await asyncio.create_task(hedge_client.start())
        asyncio.create_task(price_feeds.start_hubble_feed(hubble_client, marketID, restart_needed))
        asyncio.create_task(
            marketMaker.start_positions_feed(hubble_client, settings["orderExpiry"], restart_needed)
        )

        # # get a dict of all market ids and names - for example {0: "ETH-Perp", 1: "AVAX-Perp"}
        print(market, marketID)
        if settings["hedgeMode"]:
            asyncio.create_task(start_trader_feed(hubble_client))
        await asyncio.sleep(5)
        try:
            await marketMaker.orderUpdater(
            hubble_client,
            hedge_client if settings["hedgeMode"] else None,
            marketID,
            settings,
            active_order_direction
        )
      
        except Exception as e:
            print("Error in orderUpdater", e)
            restart_needed.set()
            return
        
        await monitor_task

    except asyncio.CancelledError:
        print("asyncio.CancelledError")

# Start and run until complete
loop = asyncio.get_event_loop()
task = loop.create_task(main(sys.argv[1]))


async def order_fill_callback(ws, response: TraderFeedUpdate):
    global active_order_direction
    global hedge_client
    if response.EventName == "OrderMatched":
        print(
            f"✅✅✅order {response.OrderId} has been filled. fillAmount: {response.Args['fillAmount']}✅✅✅"
        )
        if settings["hedgeMode"]:
            order_direction = active_order_direction.get(response.OrderId, None)
            if(order_direction is None):
                print(f"❌❌❌order {response.OrderId} not found in active_order_direction. Cant decide hedge direction❌❌❌")
                return
            await hedge_client.on_Order_Fill(response.Args["fillAmount"] * order_direction * -1)


# async def onOrderFills(
#     hubble_client: HubbleClient,
# ):
#     # listen for order fills
#     print(
#         "############################## Listening for order fills ##############################"
#     )
#     hubble_client.subscribe_to_trader_updates(ConfirmationMode.head, orderFillCallback)


async def start_trader_feed(client):
    while True:
        try:
            print("Starting trader feed...")
            await client.subscribe_to_trader_updates(
                ConfirmationMode.head, order_fill_callback
            )
        except websockets.ConnectionClosed:
            print("@@@@ trader feed: Connection dropped; attempting to reconnect...")
            await asyncio.sleep(5)  # Wait before attempting to reconnect
        except Exception as e:
            print(f"@@@@ trader feed: An error occurred: {e}")
            break  # Exit the loop if an unexpected error occurs


# Run until a certain condition or indefinitely
try:
    loop.run_until_complete(task)
except KeyboardInterrupt:
    pass
    # # Handle other shutdown signals here
    # print("CANCELLING ORDERS AND SHUTTING DOWN")
    # task = loop.create_task(marketMaker.cancelAllOrders(hubble_client, marketID))
    # # if settings["hedgeMode"]:
    # #     asyncio.run(hedge_client.exit())
    # loop.run_until_complete(task)
