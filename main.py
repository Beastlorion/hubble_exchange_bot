import sys
import os
import asyncio
import time
import ast
from hubble_exchange import HubbleClient, ConfirmationMode
from dotenv import load_dotenv, dotenv_values
import tools
from price_feeds import PriceFeed

# import marketMaker
import config
from typing import TypedDict
from hyperliquid_async import HyperLiquid
from binance_async import Binance
from orderManager import OrderManager

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


# @todo needs a restart needed event which should be triggered when an exception occurs in any task and is not resolved after max retries
# restart_needed = asyncio.Event()

# async def monitor_restart():
#     await restart_needed.wait()
#     print("Restarting application due to a task exception.")
#     # Implement your restart logic here, like exiting with a specific status code
#     sys.exit(1)


async def main(market):
    hubble_client = HubbleClient(os.environ["PRIVATE_KEY"])
    # monitor_task = asyncio.create_task(monitor_restart())

    mid_price_streaming_event = asyncio.Event()
    hubble_price_streaming_event = asyncio.Event()
    hedge_client_uptime_event = asyncio.Event()
    price_feed = PriceFeed()

    try:
        if settings["priceFeed"] == "binance-futures":
            print("Starting feed")
            await price_feed.start_binance_futures_feed(
                market, settings["futures_feed_frequency"], mid_price_streaming_event
            )
            print("Starting feed done")
        else:
            asyncio.create_task(
                price_feed.start_binance_spot_feed(market, mid_price_streaming_event)
            )
        print("Getting markets")
        markets = await hubble_client.get_markets()
        market_name = settings["name"]
        asset_name = market_name.split("-")[0]
        hubble_market_id = tools.get_key(markets, market_name)
        if settings["hedgeMode"] and settings["hedge"] == "hyperliquid":
            hedge_client = HyperLiquid(
                asset_name,
                {
                    "desired_max_leverage": settings["leverage"],
                    "slippage": settings["slippage"],
                },
            )
        elif settings["hedgeMode"] and settings["hedge"] == "binance":
            hedge_client = Binance(
                asset_name + "USDT",
                {
                    "desired_max_leverage": settings["leverage"],
                    "slippage": settings["slippage"],
                },
            )
        if settings["hedgeMode"]:
            await asyncio.create_task(
                hedge_client.start(
                    hedge_client_uptime_event,
                    settings["hedgeClient_orderbook_frequency"],
                    settings["hedgeClient_user_state_frequency"],
                )
            )
        asyncio.create_task(
            price_feed.start_hubble_feed(
                hubble_client,
                hubble_market_id,
                settings["hubble_orderbook_frequency"],
                hubble_price_streaming_event,
            )
        )
        order_manager = OrderManager()
        await asyncio.sleep(2)

        await order_manager.start(
            price_feed,
            hubble_market_id,
            settings,
            hubble_client,
            hedge_client,
            mid_price_streaming_event,
            hubble_price_streaming_event,
            hedge_client_uptime_event,
        )

        # except Exception as e:
        #     print("Error in orderUpdater", e)
        #     restart_needed.set()
        #     return

        # await monitor_task

    except asyncio.CancelledError:
        print("asyncio.CancelledError")


# Start and run until complete
loop = asyncio.get_event_loop()
task = loop.create_task(main(sys.argv[1]))


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
