import asyncio
import json
import os
import time
from aio_binance.futures.usdt.websocket.session import WebsocketSession

import numpy as np
import pandas as pd
import websockets
from aio_binance.futures.usdt import Client, WsClient
from aio_binance.error_handler.error import BinanceException
from loguru import logger as loguru_logger
# from telegram_bot import get_telegram_bot
from utils import get_logger, timeit, with_slippage

logger = get_logger()


class Binance(object):
    def __init__(
        self,
        market="AVAXUSDT",
        settings: dict = {"desired_max_leverage": 5, "slippage": 0.5},
    ):
        self.symbol = market
        self.client = Client(
            key=os.environ.get("BINANCE_API_KEY"),
            secret=os.environ.get("BINANCE_SECRET_KEY"),
        )
        # self.ws_client = None
        self.ws_client = None
        self.ask_prices = pd.DataFrame()
        self.bid_prices = pd.DataFrame()
        self.position_size = 0
        self.refresh_state_task = None
        self.sync_prices_task = None
        self.listen_key_task = None
        self.state = {}

        self.last_callback_time = None
        self.alert_threshold = 5  # Seconds

        # self.telegram = get_telegram_bot()
        self.desired_initial_leverage = settings["desired_max_leverage"]
        self.slippage = settings["slippage"]
        # disables aio_binance logs
        # loguru_logger.remove()

    async def start(self):
        # await self.client.change_private_leverage(symbol=self.symbol, leverage=5)
        await self.set_initial_leverage()
        logger.info("#### binance starting...")
        # listen_key_response = await self.client.create_private_listen_key()
        # listen_key = listen_key_response['data']['listenKey']
        listen_key = None
        # logger.info(f'#### binance listen_key = {listen_key}')
        self.ws_client = WsClient(listen_key, ping_timeout=60)
        self.order_depth_feed_task = asyncio.create_task(self.start_price_feed())
        self.refresh_state_task = asyncio.create_task(self.sync_user_state())
        # self.listen_key_task = asyncio.create_task(self.keep_listen_key_updated())

    async def exit(self):
        if self.refresh_state_task:
            self.refresh_state_task.cancel()
        if self.sync_prices_task:
            self.sync_prices_task.cancel()
        if self.listen_key_task:
            self.listen_key_task.cancel()
        # try:
        #     await self.client.delete_private_listen_key()
        # except BinanceException as e:
        #     pass

    async def keep_listen_key_updated(self):
        while True:
            try:
                await asyncio.sleep(60 * 30)
                await self.client.update_private_listen_key()
                logger.info("#### binance listen_key updated")
                # await self.telegram.send_notification("Binance listen key updated.")
            except Exception as e:
                # log the error with traceback
                logger.info(
                    f"Error: error in binance keep_listen_key_updated = {e.with_traceback()}"
                )
                await asyncio.sleep(10)

    async def set_initial_leverage(self):
        # check existing position size. Update only at the beginning
        if self.position_size == 0:
            try:

                await self.client.change_private_leverage(
                    symbol=self.symbol, leverage=self.desired_initial_leverage
                )
                logger.info(
                    f"#### binance set_initial_leverage = {self.desired_initial_leverage}"
                )
                # await self.telegram.send_notification(f"Binance initial leverage set to {self.initial_leverage}.")
            except BinanceException as e:
                logger.info(f"Error: binance set_initial_leverage = {e}")
                # await self.telegram.send_notification(f"Error: binance set_initial_leverage = {e}")
        else:
            logger.info(
                f"#### binance set_initial_leverage: position exists, not setting leverage = {self.desired_initial_leverage}"
            )
            # await self.telegram.send_notification(f"Binance position exists, not setting leverage = {self.initial_leverage}")
        # run this code independent of above
        try:
            response = await self.client.get_private_leverage_brackets(
                symbol=self.symbol
            )
            self.state.initial_leverage = response["data"]["brackets"][0][
                "initialLeverage"
            ]
        except Exception as e:
            logger.error(f"Error: binance fetch and set_initial_leverage = {e}")
            # await self.telegram.send_notification(f"Error: binance set_initial_leverage = {e}")

    async def sync_user_state(self) -> dict:
        while True:
            try:
                user_state = await self.client.get_private_account_info()
                margin = list(
                    filter(lambda x: x["asset"] == "USDT", user_state["data"]["assets"])
                )[0]
                available_margin = float(margin["walletBalance"])
                position_state = list(
                    filter(
                        lambda x: x["symbol"] == "AVAXUSDT",
                        user_state["data"]["positions"],
                    )
                )[0]
                # position_state = position_state['data'][0]
                notional = float(position_state["notional"])
                size = float(position_state["positionAmt"])
                entry_price = float(position_state["entryPrice"])
                # liquidation_px = position_state['liquidationPrice']
                # liquidation_price = float(liquidation_px) if liquidation_px else float(0)
                # unrealized_pnl = float(position_state['unRealizedProfit'])
                leverage = abs(notional / available_margin)
                self.position_size = size
                self.state = {
                    "entry_price": entry_price,
                    # 'liquidation_price': liquidation_price,
                    # 'unrealized_pnl': unrealized_pnl,
                    "size": size,
                    "leverage": leverage,
                    "available_margin": available_margin,
                }
                await asyncio.sleep(10)
            # except requests.exceptions.ConnectionError as e:
            #     logger.info(f'Error: connection error in sync_user_state = {e}')
            #     self.reset_connection()
            #     await asyncio.sleep(10)

            except Exception as e:
                logger.info(f"Error: error in binance sync_user_state = {e}")
                await asyncio.sleep(10)

    def get_state(self):
        return self.state
        # res = await self.client.get_private_account_info()
        # # res = await self.client.get_private_balance()
        # # res = await self.client.get_private_position_risk(self.symbol)
        # print(json.dumps(res, indent=4, sort_keys=True))

    async def check_callback_timeout(self):
        while True:
            if self.last_callback_time is not None:
                elapsed_time = time.time() - self.last_callback_time
                if elapsed_time > self.alert_threshold:
                    # await self.telegram.send_notification(
                    #     f"Alert: More than 5 seconds since the last callback was received. (binance_async.py)"
                    # )
                    logger.warning(
                        "Alert: More than 5 seconds since the last callback was received."
                    )
                    return
            await asyncio.sleep(5)  # Check every 5 second

    async def start_price_feed(self):
        async def callback(msg):
            self.last_callback_time = time.time()
            await self.handle_ticker(msg)

        # await self.telegram.send_notification("Binance price feed started.")
        asyncio.create_task(self.check_callback_timeout())

        while True:
            try:
                stream = await self.ws_client.stream_diff_book_depth(
                    symbol=self.symbol, speed=100
                )
                async with WebsocketSession(self.client, debug="info") as session:
                    await session.run(stream, callback)
                # stream = await self.ws_client.stream_diff_book_depth(symbol=self.symbol, speed=100, callback_event=callback)
                # stream = await self.ws_client.stream_partial_book_depth(symbol=self.symbol, level=10, speed=100, callback_event=callback)
                # logger.info('#### binance price feed: finished')
                # await self.ws_client.subscription_streams([stream], callback_event=callback)
            except websockets.exceptions.ConnectionClosed:
                logger.error(
                    "@@@@ binance price feed: Connection dropped; attempting to reconnect..."
                )
                await asyncio.sleep(5)  # Wait before attempting to reconnect

    async def maintain_connection(self, callback):
        """
        This helper function attempts to maintain the WebSocket connection.
        """
        stream = await self.ws_client.stream_diff_book_depth(
            symbol=self.symbol, speed=100, callback_event=callback
        )

    async def handle_ticker(self, data):
        try:
            ask_df = (
                pd.DataFrame(data["a"], columns=["price", "size"])
                .astype(float)
                .sort_values("price", ascending=True)
                .query("size != 0")
            )
            bid_df = (
                pd.DataFrame(data["b"], columns=["price", "size"])
                .astype(float)
                .sort_values("price", ascending=False)
                .query("size != 0")
            )
        except KeyError as e:
            ask_df = pd.DataFrame()
            bid_df = pd.DataFrame()
            logger.info(f"ERROR: KeyError: error = {e}, data = {data}")

        if ask_df.empty or bid_df.empty:
            logger.info(
                f"#### binance price feed: empty data, ask_df.empty={ask_df.empty}, bid_df.empty={bid_df.empty}"
            )
            return
        self.ask_prices = ask_df
        self.bid_prices = bid_df

    def get_prices(self):
        return self.bid_prices.to_dict("list"), self.ask_prices.to_dict("list")

    async def get_free_margin(self):
        res = await self.client.get_private_account_info()
        margin = list(filter(lambda x: x["asset"] == "USDT", res["data"]["assets"]))[0]
        return float(margin["walletBalance"])

    async def get_fill_price(self, size):
        filled_size = 0
        current_index = 0
        price = 0
        while abs(size) > filled_size:
            if size > 0:
                price = self.ask_prices.iloc[current_index].price
            else:
                price = self.bid_prices.iloc[current_index].price

            filled_size += abs(self.bid_prices.iloc[current_index].size)
            current_index += 1
        return price

    async def can_open_position(self, size):
        # freeMargin >= openNotional * marginFactor
        # openNotional = abs(size * price)
        price = await self.get_fill_price(size)
        # check if price is within index + slippage ?
        price = with_slippage(price, self.slippage, size > 0)
        return (
            self.state["available_margin"]
            >= abs(size * price) / self.state["initial_leverage"]
        )

    async def on_Order_Fill(self, size):
        # start a thread to execute trade and retry if failed
        # // check if any pending market orders. Club them ??
        # retries = get from config
        # delay = get from config
        retries = 4
        delay = 0.2
        for i in range(retries):
            try:
                # Attempt to execute the trade
                # Add your trade execution logic here
                if await self.can_open_position(size):
                    print(f"Executing trade attempt {i+1}")
                    filled_size = 0
                    # calculated only once to maintain slippage across partial fills
                    fill_price = await self.get_fill_price(size)
                    while True:
                        order_execution_response = await self.execute_market_order(
                            size - filled_size, fill_price, False, self.slippage
                        )
                        if order_execution_response["isCompletelyFilled"]:
                            print(f"Trade executed successfully on attempt {i+1}")
                            break
                        else:
                            filled_size += order_execution_response["filled_quantity"]
                            print(
                                f"Trade partially executed. Filled size = {filled_size}. Attempt {i+1}"
                            )
                else:
                    print(
                        f"Trade cannot be executed. Insufficient margin. Attempt {i+1}"
                    )
                    break
            except Exception as e:
                print(f"Trade execution failed on attempt {i+1}: {e}")
                # If this was the last attempt, re-raise the exception
                if i == retries - 1:
                    raise
                # Wait before the next attempt
                await asyncio.sleep(delay)
            else:
                # If the trade execution was successful, break the loop
                break

    async def execute_market_order(
        self, quantity, price, reduce_only=False, slippage=0
    ):
        logger.info(
            f"#### binance_execute_market_order: quantity = {quantity}, reduce_only = {reduce_only}, slippage = {slippage}"
        )
        side = "BUY" if quantity > 0 else "SELL"
        reduce_only = "true" if reduce_only else "false"

        # find price at which it can be sent to market

        response = await self.client.create_private_order(
            symbol=self.symbol,
            side=side,
            type_order="LIMIT",
            quantity=str(abs(quantity)),
            reduce_only=reduce_only,
            time_in_force="IOC",
            price=str(price),
            new_order_resp_type="RESULT",
        )

        filled_quantity = float(response["data"]["executedQty"]) * np.sign(quantity)
        self.position_size += filled_quantity

        filled_price = float(response["data"]["avgPrice"])
        if abs(filled_quantity) > 0:
            logger.info(f"#### binance trade filled quantity {filled_quantity}")
        else:
            logger.info(
                f"#### binance Market order failed; quantity = {quantity}, response = {response}, current prices = {self.bid_prices.iloc[0].price}, {self.ask_prices.iloc[0].price}"
            )

        return {
            "exchange": "binance",
            "isCompletelyFilled": filled_quantity == quantity,
            "filled_quantity": filled_quantity,
            "quantity": quantity,
            "remainingQuantity": quantity - filled_quantity,
            "price": filled_price,
        }

    async def execute_trade(self, quantity, reduce_only=False, price=None, slippage=0):
        logger.info(
            f"#### binance_execute_trade: quantity = {quantity}, reduce_only = {reduce_only}, price = {price}, slippage = {slippage}"
        )
        side = "BUY" if quantity > 0 else "SELL"
        reduce_only = "true" if reduce_only else "false"

        if slippage:
            price = with_slippage(price, slippage, side == "BUY")

        response = await self.client.create_private_order(
            symbol=self.symbol,
            side=side,
            type_order="LIMIT",
            quantity=str(abs(quantity)),
            price=str(price),
            reduce_only=reduce_only,
            time_in_force="IOC",
            new_order_resp_type="RESULT",
        )
        # print('resp = ', response)
        filled_quantity = float(response["data"]["executedQty"]) * np.sign(quantity)
        self.position_size += filled_quantity

        success = False
        filled_price = float(response["data"]["avgPrice"])
        if filled_quantity == quantity:
            logger.info("#### binance trade success")
            success = True
        else:
            logger.info(
                f"#### binance order failed; filled_quantity = {filled_quantity}, quantity = {quantity}, response = {response}, current prices = {self.bid_prices.iloc[0].price}, {self.ask_prices.iloc[0].price}"
            )

        return {
            "exchange": "binance",
            "success": success,
            "filled_quantity": filled_quantity,
            "quantity": quantity,
            "price": filled_price,
        }
