import sys, os, asyncio, time, ast
from hubble_exchange import HubbleClient, OrderBookDepthResponse, LimitOrder, IOCOrder
from dotenv import load_dotenv, dotenv_values
import tools
import price_feeds
import marketMaker
import config

env = {
    **dotenv_values(".env.shared"),
    **dotenv_values(".env.secret")
}
os.environ["HUBBLE_RPC"] = env["HUBBLE_RPC"]
os.environ["HUBBLE_WS_RPC"] = env["HUBBLE_WS_RPC"]
os.environ["HUBBLE_ENV"] = env["HUBBLE_ENV"]
os.environ["PRIVATE_KEY"] = env[sys.argv[1] + "_PRIVATE_KEY"]
os.environ["HUBBLE_INDEXER_API_URL"] = env["HUBBLE_INDEXER_API_URL"]
# settings = ast.literal_eval(env[sys.argv[1]])
settings = getattr(config, sys.argv[1])

marketID = None

restart_needed = asyncio.Event()

async def monitor_restart():
    await restart_needed.wait()
    print("Restarting application due to a task exception.")
    # Implement your restart logic here, like exiting with a specific status code
    sys.exit(1)


async def main(market):
    global marketID
    client = HubbleClient(os.environ["PRIVATE_KEY"])
    monitor_task = asyncio.create_task(monitor_restart())

    try:
        if settings["priceFeed"] == "binance-futures":
            asyncio.create_task(price_feeds.start_binance_futures_feed(market, restart_needed))
        else:
            asyncio.create_task(price_feeds.start_binance_spot_feed(market))

        markets = await client.get_markets()
        marketID = tools.getKey(markets, settings["name"])
        asyncio.create_task(price_feeds.start_hubble_feed(client, marketID, restart_needed))
        asyncio.create_task(marketMaker.start_positions_feed(client, settings['orderExpiry'], restart_needed))

        # # get a dict of all market ids and names - for example {0: "ETH-Perp", 1: "AVAX-Perp"}
        print(market,marketID)

        await asyncio.sleep(2)
        try:
            await marketMaker.orderUpdater(client, marketID, settings)
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

# Run until a certain condition or indefinitely
try:
    loop.run_until_complete(task)
except KeyboardInterrupt:
    # Handle other shutdown signals here
    print("CANCELLING ORDERS AND SHUTTING DOWN")
    task = loop.create_task(marketMaker.cancelAllOrders(client,marketID))
    loop.run_until_complete(task)
