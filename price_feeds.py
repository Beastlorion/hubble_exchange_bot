import asyncio
import json
import os

import websockets
from binance import AsyncClient, BinanceSocketManager

from hubble_exchange import HubbleClient, OrderBookDepthUpdateResponse

import tools

mid_price = 0
hubble_prices = [float('inf'), 0]  # [best_ask, best_bid]


async def start_hubble_feed(client: HubbleClient, market):
    async def callback(ws, response: OrderBookDepthUpdateResponse):
        global hubble_prices
        if len(response.bids) > 0 and float(response.bids[-1][0]) > hubble_prices[1]:
            hubble_prices[1] = float(response.bids[-1][0])
        if len(response.asks) > 0 and float(response.asks[0][0]) < hubble_prices[0]:
            hubble_prices[0] = float(response.asks[0][0])

    await client.subscribe_to_order_book_depth_with_freq(market, callback, "500ms")

async def start_binance_spot_feed(market):
    symbol = tools.getSymbolFromName(market) + "USDT"

    client = await AsyncClient.create()
    bm = BinanceSocketManager(client)
    # start any sockets here, i.e a trade socket
    ts = bm.trade_socket(symbol)
    # then start receiving messages
    async with ts as tscm:
        while True:
            res = await tscm.recv()
            priceUsdt = float(res["p"])
            global mid_price
            mid_price = priceUsdt
    await client.close_connection()


async def start_binance_futures_feed(market):
    symbol = tools.getSymbolFromName(market) + "USDT"
    print(f"Starting Binance Futures price feed for {symbol}...")
    # ws_url = f"wss://fstream.binance.com/ws/{symbol.lower()}@depth@100ms"
    ws_url = f"wss://fstream.binance.com/ws/{symbol.lower()}@bookTicker"

    retry_delay = 5  # Initial retry delay in seconds
    max_retries = 5  # Maximum number of retries
    attempt_count = 0  # Attempt counter

    while attempt_count < max_retries:
        try:
            async with websockets.connect(ws_url) as websocket:
                print("Connected to the server.")
                attempt_count = 0  # Reset attempt counter on successful connection

                while True:
                    message = await websocket.recv()
                    data = json.loads(message)
                    global mid_price
                    mid_price = round((float(data["b"]) + float(data["a"])) / 2, 5)
                    # print(f"Mid price: {mid_price}")

        except Exception as e:
            print(f"Connection error: {e}")
            attempt_count += 1
            print(f"Attempting to reconnect in {retry_delay} seconds... (Attempt {attempt_count}/{max_retries})")
            await asyncio.sleep(retry_delay)
            retry_delay *= 2  # Exponential backoff

        if attempt_count >= max_retries:
            print("Maximum retry attempts reached. Exiting.")
            break
