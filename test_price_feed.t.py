import asyncio
from price_feeds import PriceFeed
import time
import websockets
from binance import AsyncClient, BinanceSocketManager
import json
import tools


binance_futures_feed_stopped = True
mid_price = 0
mid_price_last_updated_at = 0


async def start_binance_futures_feed(market, frequency, mid_price_streaming_event):
    global binance_futures_feed_stopped
    symbol = tools.get_symbol_from_name(market) + "USDT"
    print(f"Starting Binance Futures price feed for {symbol}...")
    task = asyncio.create_task(
        subscribe_to_binance_futures_feed(symbol, frequency, mid_price_streaming_event)
    )
    print("Binance Futures price feed started.")
    return task
    # ws_url = f"wss://fstream.binance.com/ws/{symbol.lower()}@depth@100ms"


async def subscribe_to_binance_futures_feed(
    symbol, frequency, mid_price_streaming_event
):
    global binance_futures_feed_stopped
    global mid_price
    global mid_price_last_updated_at
    print(f"subscribe_to_binance_futures_feed for {symbol}...")
    ws_url = f"wss://fstream.binance.com/ws/{symbol.lower()}@bookTicker"

    retry_delay = 3  # Initial retry delay in seconds
    max_retries = 5  # Maximum number of retries
    attempt_count = 0  # Attempt counter
    next_timestamp = 0
    while True:
        try:
            async with websockets.connect(ws_url) as websocket:
                print("Connected to the server.")
                if binance_futures_feed_stopped:
                    # @todo check if this is the correct way to clear the event
                    print("setting mid_price_streaming_event")
                    mid_price_streaming_event.set()
                    binance_futures_feed_stopped = False
                attempt_count = 0  # Reset attempt counter on successful connection
                retry_delay = 3  # Reset retry delay on successful connection
                while True:
                    message = await websocket.recv()
                    data = json.loads(message)
                    # Check if the data is stale
                    if next_timestamp - float(data["T"]) / 1000 > 0:
                        print(f"skipping data: {float(data['T'])/1000}")
                        continue  # discard the data and wait for the next piece

                    print(
                        f"data fetched at time: {time.time()} lag of {time.time() - float(data['T'])/1000}"
                    )
                    print(f"binance data: {data}")
                    mid_price = round((float(data["b"]) + float(data["a"])) / 2, 5)
                    print(f"Mid price: {mid_price}")
                    mid_price_last_updated_at = time.time()
                    print(f"sleeping at {time.time()}")
                    next_timestamp = time.time() + frequency
                    # await asyncio.sleep(frequency)
                    print(f"woke up at {time.time()}")

        except Exception as e:
            if attempt_count >= max_retries:
                # @todo check how to bubble the exception
                print("Maximum retry attempts reached. Exiting.")
                break
            mid_price_streaming_event.clear()
            binance_futures_feed_stopped = True
            print(f"Binance futures feed connection error: {e}")
            attempt_count += 1
            print(
                f"Attempting to reconnect in {retry_delay} seconds... (Attempt {attempt_count}/{max_retries})"
            )
            await asyncio.sleep(retry_delay)
            retry_delay *= 2  # Exponential backoff


async def test_price_feed():
    mid_price_streaming_event = asyncio.Event()
    task = await start_binance_futures_feed("AVAX-USDT", 1, mid_price_streaming_event)
    await task


# Start and run until complete
asyncio.run(test_price_feed())
