import asyncio
import time
import csv
import json
import os
from datetime import datetime
from typing import Any, List, Literal
import aiohttp
from aiohttp import ClientResponse
import eth_account
import numpy as np
import pandas as pd
import requests
from hyperliquid.exchange import Exchange
from hyperliquid.info import Info
from hyperliquid.utils import constants
from hyperliquid.utils.error import ClientError, ServerError
from hyperliquid.utils.signing import (
    ZERO_ADDRESS,
    OrderRequest,
    OrderSpec,
    get_timestamp_ms,
    order_grouping_to_number,
    order_request_to_order_spec,
    order_spec_preprocessing,
    order_spec_to_order_wire,
    sign_l1_action,
)
from hyperliquid.utils.types import L2BookSubscription, TradesSubscription
from utils import get_logger, timeit, with_slippage

logger = get_logger()


class HyperLiquid:
    price_feed_last_updated = None

    def __init__(
        self, market: str, settings: dict = {"desired_max_leverage": 5, "slippage": 0.5}
    ):
        """
        Initializes the HyperLiquid class with necessary API connections and account information.
        """
        self.info = Info(constants.MAINNET_API_URL, skip_ws=False)
        self.account = eth_account.Account.from_key(
            os.environ["HYPERLIQUID_PRIVATE_KEY"]
        )
        self.trader_address = os.environ["HYPERLIQUID_TRADER"]
        self.exchange = Exchange(self.account, constants.MAINNET_API_URL)

        self.market = market.upper()
        self.ask_prices = pd.DataFrame()
        self.bid_prices = pd.DataFrame()

        self.subscription = L2BookSubscription({"type": "l2Book", "coin": self.market})
        self.subscription_id = None

        self.position_size = 0
        self.refresh_state_task = None
        self.sync_prices_task = None
        self.state = {}
        self.session = None
        self.desired_max_leverage = settings["desired_max_leverage"]
        self.slippage = settings["slippage"]
        self.is_price_feed_down = True
        self.is_trader_feed_down = True
        self.hedge_client_uptime_event = None

    def reset_connection(self):
        self.info = Info(constants.MAINNET_API_URL, skip_ws=False)
        self.account = eth_account.Account.from_key(
            os.environ["HYPERLIQUID_PRIVATE_KEY"]
        )
        self.trader_address = os.environ["HYPERLIQUID_TRADER"]
        self.exchange = Exchange(self.account, constants.MAINNET_API_URL)

    async def start(
        self,
        hedge_client_uptime_event: asyncio.Event,
        orderbook_frequency=5,
        user_state_frequency=5,
    ):
        print("Starting HyperLiquid...")
        self.hedge_client_uptime_event = hedge_client_uptime_event
        await self.set_initial_leverage()
        self.refresh_state_task = asyncio.create_task(
            self.sync_user_state(user_state_frequency)
        )
        self.sync_prices_task = asyncio.create_task(
            self.sync_prices(orderbook_frequency)
        )
        await asyncio.sleep(5)

    async def exit(self):
        self.info.unsubscribe(self.subscription, self.subscription_id)
        if self.refresh_state_task:
            self.refresh_state_task.cancel()
        if self.sync_prices_task:
            self.sync_prices_task.cancel()
        await self.close_session()

    # def start_price_feed(self):
    #     def callback(feed):
    #         if self.is_price_feed_down:
    #             self.is_price_feed_down = False
    #             self.hedge_client_uptime_event.set()
    #         asyncio.run(self.update_prices(feed))

    #     self.subscription_id = self.info.subscribe(self.subscription, callback)

    #     def on_close(*args):
    #         logger.error(f"@@@@ hyper on close args = {args}")
    #         self.is_price_feed_down = True
    #         self.hedge_client_uptime_event.clear()
    #         self.reset_connection()

    #     self.info.ws_manager.ws.on_close = on_close

    #     def on_error(*args):
    #         logger.error(f"@@@@ hyper on error; args = {args}")
    #         self.is_price_feed_down = True
    #         self.hedge_client_uptime_event.clear()
    #         self.reset_connection()

    #     self.info.ws_manager.ws.on_error = on_error

    async def update_prices(self, data):
        bid_data, ask_data = data["data"]["levels"][0], data["data"]["levels"][1]
        bid_df = (
            pd.DataFrame(bid_data, columns=["n", "px", "sz"])
            .astype(float)
            .rename(columns={"px": "price", "sz": "size"})
            .drop(columns=["n"])
        )
        ask_df = (
            pd.DataFrame(ask_data, columns=["n", "px", "sz"])
            .astype(float)
            .rename(columns={"px": "price", "sz": "size"})
            .drop(columns=["n"])
        )
        self.ask_prices = ask_df
        self.bid_prices = bid_df
        self.price_feed_last_updated = time.time()

    def get_prices(self):
        return self.bid_prices.to_dict("list"), self.ask_prices.to_dict("list")

    async def set_initial_leverage(self):
        # check existing position size. Update only at the beginning
        if self.position_size == 0:
            try:
                logger.info(
                    f"Setting Hyperliquid initial leverage to {self.desired_max_leverage}."
                )
                self.exchange.update_leverage(self.desired_max_leverage, self.market)
                logger.info(
                    f"Hyperliquid initial leverage set to {self.desired_max_leverage}."
                )
                # await self.telegram.send_notification(f"Hyperliquid initial
                # leverage set to {self.initial_leverage}.")
            except Exception as e:
                logger.info("Error: Hyperliquid set_initial_leverage = %s", e)
                # await self.telegram.send_notification(f"Error: Hyperliquid
                # set_initial_leverage = {e}")
        else:
            logger.info(
                f"#### Hyperliquid set_initial_leverage: position already exists, not setting leverage = {self.desired_max_leverage}"
            )
            # await self.telegram.send_notification(f"Hyperliquid position
            # exists, not setting leverage = {self.initial_leverage}")

    @timeit
    async def get_fresh_prices(self):
        """
        Retrieves and processes the bid and ask prices for AVAX.

        :return: A tuple containing processed bid and ask dataframes.
        """
        # Retrieve level 2 snapshot of AVAX market
        start = datetime.utcnow().timestamp()
        response = await self.post("/info", {"type": "l2Book", "coin": self.market})
        # print('response time', datetime.utcnow().timestamp() - start )
        # levels = self.info.l2_snapshot(self.market)['levels']
        bid_data, ask_data = response["levels"]

        # Process bid and ask dataframes
        bid_df = pd.DataFrame(bid_data, columns=["n", "px", "sz"]).astype(float)
        ask_df = pd.DataFrame(ask_data, columns=["n", "px", "sz"]).astype(float)

        # Sort and select relevant data
        bid_df = (
            bid_df.sort_values("px", ascending=False).reset_index(drop=True).iloc[0]
        )
        ask_df = ask_df.sort_values("px", ascending=True).reset_index(drop=True).iloc[0]

        return bid_df.px, ask_df.px

    async def sync_prices(self, frequency) -> dict:
        cooldown = 2
        retry_count = 0
        max_retries = 5
        while True:
            try:
                response = await self.post(
                    "/info", {"type": "l2Book", "coin": self.market}
                )
                if self.is_price_feed_down:
                    self.is_price_feed_down = False
                    self.hedge_client_uptime_event.set()
                    cooldown = 2
                    retry_count = 0
                # print('#### sync_prices', datetime.utcnow().timestamp() -
                # start)
                modded_response = {"data": response}

                await self.update_prices(modded_response)
                # logger.info("#### hyper price state updated")
                await asyncio.sleep(frequency)
            except requests.exceptions.ConnectionError as e:
                logger.info(f"Error: connection error in sync_prices = {e}")
                retry_count += 1
                if retry_count > max_retries:
                    self.is_price_feed_down = True
                    self.hedge_client_uptime_event.clear()
                    self.reset_connection()
                cooldown = 2**retry_count
                self.reset_connection()
                await asyncio.sleep(cooldown)

            # except Exception as e:
            #     logger.info(f"Error: error in sync_prices = {e}")
            #     await asyncio.sleep(2)

    async def sync_user_state(self, user_state_frequency) -> dict:
        while True:
            try:
                user_state = await self.post(
                    "/info", {"type": "clearinghouseState", "user": self.trader_address}
                )
                if self.is_trader_feed_down:
                    self.is_trader_feed_down = False
                    print("setting hedge_client_uptime_event")
                    self.hedge_client_uptime_event.set()
                # logger.info(json.dumps(user_state, indent=4, sort_keys=True))
                market_position = next(
                    (
                        x
                        for x in user_state["assetPositions"]
                        if x["position"]["coin"] == self.market
                    ),
                    None,
                )
                if market_position is None:
                    self.position_size = 0
                    self.state = {
                        "entry_price": 0,
                        "liquidation_price": 0,
                        "unrealized_pnl": 0,
                        "size": 0,
                        "leverage": 0,
                        "available_margin": float(
                            user_state["crossMarginSummary"]["accountValue"]
                        )
                        - float(user_state["crossMarginSummary"]["totalMarginUsed"]),
                    }
                    # logger.info('#### hyper state updated')
                    await asyncio.sleep(10)
                    continue
                entry_price = float(market_position["position"]["entryPx"])
                liquidationPx = market_position["position"]["liquidationPx"]
                liquidation_price = float(liquidationPx) if liquidationPx else float(0)
                unrealized_pnl = float(market_position["position"]["unrealizedPnl"])
                size = float(market_position["position"]["szi"])
                margin_summary = user_state["crossMarginSummary"]
                leverage = float(margin_summary["totalNtlPos"]) / float(
                    margin_summary["accountValue"]
                )
                self.position_size = size

                self.state = {
                    "entry_price": entry_price,
                    "liquidation_price": liquidation_price,
                    "unrealized_pnl": unrealized_pnl,
                    "size": size,
                    "leverage": leverage,
                    "available_margin": float(
                        user_state["crossMarginSummary"]["accountValue"]
                    )
                    - float(user_state["crossMarginSummary"]["totalMarginUsed"]),
                }
                # logger.info("#### hyper user state updated")
                await asyncio.sleep(user_state_frequency)
            except requests.exceptions.ConnectionError as e:
                logger.info(f"Error: connection error in sync_user_state = {e}")
                self.is_trader_feed_down = True
                self.hedge_client_uptime_event.clear()
                self.reset_connection()
                await asyncio.sleep(2)

            except Exception as e:
                logger.info(f"Error: error in sync_user_state = {e}")
                self.is_trader_feed_down = True
                self.hedge_client_uptime_event.clear()
                await asyncio.sleep(2)

    def get_state(self):
        return self.state

    def get_mid(self):
        return (self.bid_prices.iloc[0].price + self.ask_prices.iloc[0].price) / 2

    def get_fill_price(self, size):
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

    # @todo account for reducing position size
    def can_open_position(self, size):
        price = self.get_fill_price(size)
        price = with_slippage(price, self.slippage, size > 0)
        return (
            self.state["available_margin"]
            >= abs(size * price) / self.desired_max_leverage
        )

    async def on_Order_Fill(self, size):
        # start a thread to execute trade and retry if failed
        # // check if any pending market orders. Club them ??
        # retries = get from config
        # delay = get from config
        retries = 4
        delay = 0.2
        filled_size = 0
        fill_price = self.get_fill_price(size)
        final_avg_fill_price = 0
        total_fee = 0
        if self.can_open_position(size):
            for i in range(retries):
                try:
                    print(
                        f"✅✅✅✅✅✅✅✅Executing hedge trade attempt {i+1}✅✅✅✅✅✅✅"
                    )
                    order_execution_response = await self.execute_trade(
                        size - filled_size, False, fill_price, self.slippage
                    )
                    final_avg_fill_price += order_execution_response["price"] * (
                        order_execution_response["filled_quantity"] / size
                    )
                    # total_fee += order_execution_response["trade_fee"]
                    if order_execution_response["isCompletelyFilled"]:
                        print(
                            f"Hedge Trade executed successfully on attempt {i+1}, Opened a position of size {size}."
                        )

                        break
                    else:
                        filled_size += order_execution_response["filled_quantity"]
                        print(f"Trade partially executed. Filled size = {filled_size}.")
                except Exception as e:
                    print(f"Trade execution failed on attempt {i+1}: {e}")
                    # If this was the last attempt, re-raise the exception
                    if i == retries - 1:
                        raise
                    # Wait before the next attempt
                    await asyncio.sleep(delay)
            # @todo return taker fee as well
            return final_avg_fill_price
        else:
            print(f"Hedge Trade cannot be executed. Insufficient margin. Attempt {i+1}")

    @timeit
    async def execute_trade(self, quantity, reduce_only=False, price=None, slippage=0):
        if not price and not reduce_only:
            raise ValueError("Hyperliquid: Price must be set for non-reduce only")
        # Determine the trade type (buy or sell)
        side = np.sign(quantity)
        if side == 1:
            is_buy = True
        else:
            is_buy = False

        if slippage:
            price = with_slippage(price, slippage, is_buy)

        order: OrderRequest = {
            "coin": self.market,
            "is_buy": is_buy,
            "sz": abs(quantity),
            "limit_px": price,
            "order_type": {"limit": {"tif": "Ioc"}},
            "reduce_only": reduce_only,
        }

        order_specs: List[OrderSpec] = [
            order_request_to_order_spec(
                order, self.exchange.coin_to_asset[order["coin"]]
            )
        ]
        timestamp = get_timestamp_ms()
        grouping: Literal["na"] = "na"
        signature_types = ["(uint32,bool,uint64,uint64,bool,uint8,uint64)[]", "uint8"]
        signature = sign_l1_action(
            self.exchange.wallet,
            signature_types,
            [
                [order_spec_preprocessing(order_spec) for order_spec in order_specs],
                order_grouping_to_number(grouping),
            ],
            (
                ZERO_ADDRESS
                if self.exchange.vault_address is None
                else self.exchange.vault_address
            ),
            timestamp,
            True,  # is_mainnet
        )

        payload = {
            "action": {
                "type": "order",
                "grouping": grouping,
                "orders": [
                    order_spec_to_order_wire(order_spec) for order_spec in order_specs
                ],
            },
            "nonce": timestamp,
            "signature": signature,
            "vaultAddress": self.exchange.vault_address,
        }

        error = None
        logger.info("hyperliquid sending order now")
        tx = None
        try:
            tx = await self.post("/exchange", payload)
        except requests.exceptions.ConnectionError as e:
            logger.info(f"Error: connection error in execute_trade = {e}")
            self.reset_connection()
            raise e
        except Exception as e:
            logger.info(f"Error: error in execute_trade = {e}")
            error = e
            raise e

        filled_quantity = 0
        avg_fill_price = 0
        try:
            filled_quantity = (
                float(tx["response"]["data"]["statuses"][0]["filled"]["totalSz"]) * side
            )
            avg_fill_price = float(
                tx["response"]["data"]["statuses"][0]["filled"]["avgPx"]
            )

        except KeyError as e:
            logger.info(f"Error: in execute_trade, tx = {tx}")

        success = False
        self.position_size += filled_quantity
        if abs(filled_quantity) > 0:
            logger.info("hyerliquid trade success")
        else:
            logger.info(
                f"hyperliquid trade failed, price = {price}, filled_quantity = {filled_quantity}, quantity = {quantity}; current prices = bid = {self.bid_prices.iloc[0].price}, ask = {self.ask_prices.iloc[0].price}"
            )
            logger.info(f"hyperliquid respose = {tx}")

        # return {
        #     "exchange": "hyperliquid",
        #     "success": success,
        #     "filled_quantity": filled_quantity,
        #     "quantity": quantity,
        #     "price": price,
        # }
        return {
            "exchange": "binance",
            "isCompletelyFilled": filled_quantity == quantity,
            "filled_quantity": filled_quantity,
            "quantity": quantity,
            "remainingQuantity": quantity - filled_quantity,
            "price": avg_fill_price,
            # @todo add trade fee here
            # "trade_fee":
        }

    async def get_session(self) -> aiohttp.ClientSession:
        if self.session is None or self.session.closed:
            self.session = aiohttp.ClientSession(headers={"Connection": "keep-alive"})
        return self.session

    async def post(self, url_path: str, payload: Any = None) -> Any:
        if payload is None:
            payload = {}

        url = constants.MAINNET_API_URL + url_path

        session = await self.get_session()  # Ensure the session is ready

        response = await session.post(url, json=payload)
        await self._handle_exception(response)

        try:
            return await response.json()
        except ValueError:
            return {"error": f"Could not parse JSON: {await response.text()}"}

    async def close_session(self):
        if self.session and not self.session.closed:
            await self.session.close()

    async def _handle_exception(self, response: ClientResponse):
        status_code = response.status
        if status_code < 400:
            return
        if 400 <= status_code < 500:
            try:
                response.json()
                err = json.loads(response.text)
            except json.JSONDecodeError:
                raise ClientError(
                    status_code, None, response.text, None, response.headers
                )
            error_data = None
            if "data" in err:
                error_data = err["data"]
            raise ClientError(
                status_code, err["code"], err["msg"], response.headers, error_data
            )
        raise ServerError(status_code, response.text)
