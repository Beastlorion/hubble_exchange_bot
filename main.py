import sys, os, asyncio, time, ast
from hubble_exchange import HubbleClient, OrderBookDepthResponse, LimitOrder, IOCOrder
from dotenv import load_dotenv, dotenv_values
import tools
import price_feeds
import marketMaker

config = {
    **dotenv_values(".env.shared"),
    **dotenv_values(".env.secret")
}
os.environ["HUBBLE_RPC"] = config["HUBBLE_RPC"]
os.environ["HUBBLE_WS_RPC"] = config["HUBBLE_WS_RPC"]
os.environ["HUBBLE_ENV"] = config["HUBBLE_ENV"]
os.environ["PRIVATE_KEY"] = config[sys.argv[1] + "_PRIVATE_KEY"]
os.environ["HUBBLE_INDEXER_API_URL"] = config["HUBBLE_INDEXER_API_URL"]
settings = ast.literal_eval(config[sys.argv[1]])

client = {}
marketID = None

async def main(market):
    global client
    global marketID
    client = HubbleClient(config["PRIVATE_KEY"])
    
    try:
        price_feeds.startPriceFeed(market)

        # # get a dict of all market ids and names - for example {0: "ETH-Perp", 1: "AVAX-Perp"}
        markets = await client.get_markets()
        marketID = tools.getKey(markets,settings["name"])
        print(market,marketID)
        
        await asyncio.sleep(2)
        await marketMaker.orderUpdater(client,marketID,settings)
        
    except asyncio.CancelledError:
        print("asyncio.CancelledError")
    finally:
        await marketMaker.cancelAllOrders(client, marketID)

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
