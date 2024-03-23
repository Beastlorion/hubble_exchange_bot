import asyncio
import time
import csv
from decimal import *
import json
from hexbytes import HexBytes
from hubble_exchange import HubbleClient, ConfirmationMode
from hubble_exchange.constants import get_minimum_quantity, get_price_precision
from hubble_exchange.models import TraderFeedUpdate
from hubble_exchange.utils import int_to_scaled_float
from hyperliquid_async import HyperLiquid
from binance_async import Binance
import tools
from enum import Enum
import cachetools
import websockets


class OrderManager:
    client: HubbleClient
    market: str
    settings: dict
    hedge_client: HyperLiquid or Binance
    order_data: cachetools.TTLCache
    price_feed: None
    trader_data: None
    trader_data_last_updated_at: 0
    market_position: None
    mid_price: None
    mid_price_last_updated_at: 0
    position_polling_task: None
    create_orders_task: None
    order_fill_cooldown_triggered = False
    is_order_fill_active = False
    is_trader_position_feed_active = False
    save_performance_task: None
    start_time = 0

    performance_data = {
        "start_time": 0,
        "end_time": 0,
        "total_trade_volume": 0,
        "trade_volume_in_period": 0,
        "orders_attempted": 0,
        "orders_placed": 0,
        "orders_filled": 0,
        "orders_failed": 0,
        "orders_hedged": 0,
        "hedge_spread_pnl": 0,
        "taker_fee": 0,
        "maker_fee": 0,
    }

    async def start(
        self,
        price_feed,
        market: str,
        settings: dict,
        client: HubbleClient,
        hedge_client: HyperLiquid or Binance,
        mid_price_streaming_event: asyncio.Event,
        hubble_price_streaming_event: asyncio.Event,
        hedge_client_uptime_event: asyncio.Event,
    ):
        self.start_time = time.strftime("%d-%m-%Y %H:%M")
        self.client = client
        self.settings = settings
        self.hedge_client = hedge_client
        self.market = market
        self.order_data = cachetools.TTLCache(
            maxsize=128, ttl=self.settings["orderExpiry"] + 2
        )
        self.price_feed = price_feed
        # monitor_task = asyncio.create_task(self.monitor_restart())
        t1 = asyncio.create_task(self.start_order_fill_feed())
        t2 = asyncio.create_task(
            self.start_trader_positions_feed(settings["hubblePositionPollInterval"])
        )

        self.save_performance_task = asyncio.create_task(self.save_performance())

        # this task can be on demand paused and started
        self.create_orders_task = asyncio.create_task(
            self.create_orders(
                mid_price_streaming_event,
                hubble_price_streaming_event,
                hedge_client_uptime_event,
            )
        )
        print("returning tasks from order manager")
        future = await asyncio.gather(
            t1, t2, self.create_orders_task, self.save_performance_task
        )
        return future

    def is_stale_data(
        self,
        mid_price_update_time,
        price_expiry,
        position_last_update_time,
        position_expiry,
    ):
        return (
            time.time() - mid_price_update_time > price_expiry
            or time.time() - position_last_update_time > position_expiry
        )

    async def create_orders(
        self,
        mid_price_streaming_event,
        hubble_price_streaming_event,
        hedge_client_uptime_event,
    ):
        while True:
            # check for all services to be active
            await mid_price_streaming_event.wait()
            await hubble_price_streaming_event.wait()
            if self.settings["hedgeMode"]:
                await hedge_client_uptime_event.wait()

            # print("####### all clear #######")

            if (
                self.is_order_fill_active is False
                or self.is_trader_position_feed_active is False
            ):
                print(
                    "Hubble OrderFill feed or Trader Hubble position feed not running. Retrying in 5 seconds..."
                )
                await asyncio.sleep(5)
                continue
            # get mid price
            if self.order_fill_cooldown_triggered:
                print("order fill cooldown triggered, skipping order creation")
                await asyncio.sleep(self.settings["orderFrequency"])
                continue
            self.mid_price = self.price_feed.get_mid_price()
            self.mid_price_last_updated_at = (
                self.price_feed.get_mid_price_last_update_time()
            )
            # if self.mid_price is None or self.mid_price == 0:
            #     await asyncio.sleep(2)
            #     return
            # print("mid price", self.mid_price)
            # print("mid_price_last_updated_at", self.mid_price_last_updated_at)
            # print("trader_data_last_updated_at", self.trader_data_last_updated_at)
            if self.is_stale_data(
                self.mid_price_last_updated_at,
                self.settings["mid_price_expiry"],
                self.trader_data_last_updated_at,
                self.settings["position_data_expiry"],
            ):
                # todo handle better or with config.
                print("stale data, skipping order creation")
                await asyncio.sleep(self.settings["orderFrequency"])
                continue

            free_margin_ask, free_margin_bid, defensive_skew_ask, defensive_skew_bid = (
                self.get_free_margin_and_defensive_skew()
            )

            buy_orders = await self.generate_buy_orders(
                free_margin_bid,
                defensive_skew_bid,
            )
            sell_orders = await self.generate_sell_orders(
                free_margin_ask,
                defensive_skew_ask,
            )
            signed_orders = []
            signed_orders = buy_orders + sell_orders

            if len(signed_orders) > 0:
                order_time = time.strftime("%H:%M::%S")
                print(f"placing {len(signed_orders)} orders, time - {order_time}")
                await self.place_orders(signed_orders)

            # pause for expiry duration
            await asyncio.sleep(self.settings["orderFrequency"])

    async def set_order_fill_cooldown(self):
        self.order_fill_cooldown_triggered = True
        await asyncio.sleep(self.settings["orderFillCooldown"])
        self.order_fill_cooldown_triggered = False

    # @todo need to add reporting tools to it.
    async def place_orders(self, signed_orders):
        try:
            placed_orders = await self.client.place_signed_orders(
                signed_orders, tools.generic_callback
            )
            self.performance_data["orders_attempted"] += len(placed_orders)
            for idx, order in enumerate(placed_orders):
                price = int_to_scaled_float(signed_orders[idx].price, 6)
                quantity = int_to_scaled_float(
                    signed_orders[idx].base_asset_quantity, 18
                )
                if order["success"]:
                    self.performance_data["orders_placed"] += 1
                    print(f"{order['order_id']}: {quantity}@{price} : ✅")
                    self.order_data[order["order_id"]] = signed_orders[idx]
                else:
                    self.performance_data["orders_failed"] += 1
                    print(
                        f"{order['order_id']}: {quantity}@{price} : ❌; {order['error']}"
                    )
        except Exception as error:
            print("failed to place orders", error)

    # only supports cross margin mode
    def get_free_margin_and_defensive_skew(self):
        total_margin = float(self.trader_data.margin)
        total_notional = 0
        u_pnl = 0
        # @todo add this
        pending_funding = 0

        for position in self.trader_data.positions:
            u_pnl += float(position["unrealisedProfit"])
            total_notional += float(position["notionalPosition"])
            if position["market"] == self.market:
                self.market_position = position

        used_margin = total_notional / float(self.settings["leverage"])
        reserved_margin = float(self.trader_data.reservedMargin)

        # print(total_margin, used_margin, u_pnl, pending_funding, reserved_margin)

        # @todo reserved margin for current open orders need to be accounted
        free_margin = (
            total_margin - used_margin + u_pnl - pending_funding - reserved_margin
        )
        margin_allocated_for_market = free_margin * float(self.settings["marginShare"])
        defensive_skew = self.settings["defensiveSkew"]
        defensive_skew_bid = 0
        defensive_skew_ask = 0
        margin_bid = margin_allocated_for_market
        margin_ask = margin_allocated_for_market
        if self.market_position and float(self.market_position["size"]) > 0:
            margin_used_for_position = float(
                float(self.market_position["notionalPosition"])
            ) / float(self.settings["leverage"])
            margin_ask = (free_margin + margin_used_for_position) * float(
                self.settings["marginShare"]
            )
            multiple = (
                float(self.market_position["notionalPosition"])
                / float(self.settings["leverage"])
            ) / free_margin
            defensive_skew_bid = multiple * 10 * defensive_skew / 100

        if self.market_position and float(self.market_position["size"]) < 0:
            margin_used_for_position = float(
                float(self.market_position["notionalPosition"])
            ) / float(self.settings["leverage"])
            # @todo check if for reduce only orders we need to add the margin_used_for_position
            margin_bid = (free_margin + margin_used_for_position) * float(
                self.settings["marginShare"]
            )
            multiple = (
                float(self.market_position["notionalPosition"])
                / float(self.settings["leverage"])
            ) / free_margin
            defensive_skew_ask = multiple * 10 * defensive_skew / 100
        # print("margin_ask, margin_bid, defensive_skew_ask, defensive_skew_bid")
        # print(margin_ask, margin_bid, defensive_skew_ask, defensive_skew_bid)
        return (margin_ask, margin_bid, defensive_skew_ask, defensive_skew_bid)

    async def generate_buy_orders(
        self,
        available_margin,
        defensive_skew,
    ):
        # print("generating buy orders")
        orders = []
        leverage = float(self.settings["leverage"])
        for level in self.settings["orderLevels"]:
            order_level = self.settings["orderLevels"][level]
            spread = float(order_level["spread"]) / 100 + defensive_skew
            bid_price = self.mid_price * (1 - spread)
            rounded_bid_price = round(bid_price, get_price_precision(self.market))
            # following should not block the execution
            try:
                best_ask_on_hubble = self.price_feed.get_hubble_prices()[0]
                if self.settings.get("avoidCrossing", False):
                    # shift the spread to avoid crossing
                    if rounded_bid_price >= best_ask_on_hubble:
                        bid_price = best_ask_on_hubble * (1 - spread)
                        rounded_bid_price = round(
                            bid_price, get_price_precision(self.market)
                        )
            except Exception as e:
                # @todo add better handling
                print("failed to get best ask on hubble", e)
                # continue with execution of rest of the function

            max_position_size = (available_margin * leverage) / rounded_bid_price
            qty = self.get_qty(order_level, max_position_size)
            # check if this is hedgable
            if self.hedge_client is not None:
                if self.hedge_client.can_open_position(qty) is False:
                    print("not enough margin to hedge position")
                    continue

            reduce_only = False
            if qty == 0:
                continue
            # @todo enable this when we have reduce only orders enabled for maker book
            # elif currentSize < 0 and qty * -1 >= currentSize + amountOnOrder:
            #     reduce_only = True
            #     amountOnOrder = amountOnOrder + qty
            available_margin = available_margin - ((qty * rounded_bid_price) / leverage)

            order = self.client.prepare_signed_order(
                self.market,
                qty,
                rounded_bid_price,
                reduce_only,
                self.settings["orderExpiry"],
            )

            orders.append(order)
        return orders

    async def generate_sell_orders(
        self,
        available_margin,
        defensive_skew,
    ):
        # print("generating sell orders")
        orders = []
        leverage = float(self.settings["leverage"])
        for level in self.settings["orderLevels"]:
            order_level = self.settings["orderLevels"][level]
            spread = float(order_level["spread"]) / 100 + defensive_skew
            ask_price = self.mid_price * (1 + spread)
            rounded_ask_price = round(ask_price, get_price_precision(self.market))
            if self.settings.get("avoidCrossing", False):
                best_bid_on_hubble = self.price_feed.get_hubble_prices()[1]
                if rounded_ask_price <= best_bid_on_hubble:
                    ask_price = best_bid_on_hubble * (1 + spread)
                    rounded_ask_price = round(
                        ask_price, get_price_precision(self.market)
                    )

            max_position_size = (available_margin * leverage) / rounded_ask_price
            qty = self.get_qty(order_level, max_position_size) * -1
            if self.hedge_client is not None:
                if self.hedge_client.can_open_position(qty) is False:
                    print("not enough margin to hedge position")
                    continue

            reduce_only = False
            if qty == 0:
                continue
            # @todo enable this when we have reduce only orders enabled for maker book
            # elif currentSize > 0 and qty * -1 <= currentSize + amountOnOrder:
            #     reduce_only = True
            #     amountOnOrder = amountOnOrder + qty
            available_margin = available_margin - ((qty * rounded_ask_price) / leverage)
            # order = LimitOrder.new(self.market, qty, rounded_ask_price, reduce_only, True)
            order = self.client.prepare_signed_order(
                self.market,
                qty,
                rounded_ask_price,
                reduce_only,
                self.settings["orderExpiry"],
            )
            orders.append(order)
        return orders

    def get_qty(self, level, max_position_size):
        if float(level["qty"]) < max_position_size:
            return float(level["qty"])
        elif max_position_size > get_minimum_quantity(self.market):
            return float(
                Decimal(str(max_position_size)).quantize(
                    Decimal(str(get_minimum_quantity(self.market))), rounding=ROUND_DOWN
                )
            )
        else:
            return 0

    # For trader Positions data feed
    async def start_trader_positions_feed(self, poll_interval):
        while True:
            try:
                self.trader_data = await self.client.get_margin_and_positions(
                    tools.generic_callback
                )
                if self.is_trader_position_feed_active is False:
                    self.is_trader_position_feed_active = True
                self.trader_data_last_updated_at = time.time()
                await asyncio.sleep(poll_interval)
            except Exception as error:
                self.is_trader_position_feed_active = False
                print("failed to get trader data", error)
                await asyncio.sleep(poll_interval)

    async def get_order_data(self, order_id):
        return self.order_data.get(order_id)

    # For order fill callbacks

    async def order_fill_callback(self, ws, response: TraderFeedUpdate):
        if response.EventName == "OrderMatched":
            print(
                f"✅✅✅order {response.OrderId} has been filled. fillAmount: {response.Args['fillAmount']}✅✅✅"
            )
            if self.settings["hedgeMode"]:
                order_data = self.order_data.get(response.OrderId, None)
                # self.performance_data["maker_fee"] += response.Args["openInterestNotional"] * trading fee percentage
                if order_data is None:
                    print(
                        f"❌❌❌order {response.OrderId} not found in placed_orders_data. Cant decide hedge direction❌❌❌"
                    )
                    return

                ## update performance data
                self.performance_data["orders_filled"] += 1
                self.performance_data["trade_volume"] += response.Args[
                    "fillAmount"
                ]  # fillAmount is abs value
                self.performance_data["cumulative_trade_volume"] += response.Args[
                    "fillAmount"
                ]  # fillAmount is abs value

                order_direction = 1 if order_data.base_asset_quantity > 0 else -1
                print(
                    f"hedging order fill, fillAmount: {response.Args['fillAmount']}, order_data: {order_data}"
                )
                try:
                    # @todo add taker fee data here
                    avg_hedge_price = await self.hedge_client.on_Order_Fill(
                        response.Args["fillAmount"] * order_direction * -1
                    )
                except Exception as e:
                    print(f"failed to hedge order fill: {e}")
                    # exit the application

            self.performance_data["orders_hedged"] += 1
            instant_pnl = 0
            if order_direction == 1:
                instant_pnl = response.Args["fillAmount"] * (
                    avg_hedge_price - response.Args["fillPrice"]
                )
            else:
                instant_pnl = response.Args["fillAmount"] * (
                    response.Args["fillPrice"] - avg_hedge_price
                )

            self.performance_data["hedge_spread_pnl"] += instant_pnl
            await self.set_order_fill_cooldown()

    async def start_order_fill_feed(self):
        while True:
            try:
                self.is_order_fill_active = True
                print(
                    "Starting hubble trader feed to listen to order fill callbacks..."
                )
                await self.client.subscribe_to_trader_updates(
                    ConfirmationMode.head, self.order_fill_callback
                )

            except websockets.ConnectionClosed:
                self.is_order_fill_active = False
                print(
                    "@@@@ trader feed: Connection dropped; attempting to reconnect..."
                )
                await asyncio.sleep(5)  # Wait before attempting to reconnect
            except Exception as e:
                self.is_order_fill_active = False
                # close the bot if an unexpected error occurs
                print(f"@@@@ trader feed: An error occurred: {e}")
                await self.set_order_fill_cooldown()

                break  # Exit the loop if an unexpected error occurs

    async def save_performance(self):
        print(f"saving performance data, data: {self.performance_data}")
        filename = (
            f"performance/performance_data_market_{self.market} {self.start_time}.csv"
        )
        while True:
            with open(filename, "a", newline="", encoding="utf-8") as csvfile:
                # Create a CSV writer
                writer = csv.writer(csvfile)
                if csvfile.tell() == 0:
                    # Write the header row
                    writer.writerow(self.performance_data.keys())

                self.performance_data["end_time"] = time.strftime("%d-%m %H:%M:%S")
                # Write the data row
                writer.writerow(self.performance_data.values())
                # await loop.run_in_executor(
                #     None, writer.writerow, self.performance_data.values()
                # )
                # clear the performance data
                self.performance_data = {
                    "start_time": time.strftime("%d-%m %H:%M:%S"),
                    "end_time": 0,
                    "total_trade_volume": self.performance_data["total_trade_volume"],
                    "trade_volume_in_period": 0,
                    "orders_attempted": 0,
                    "orders_placed": 0,
                    "orders_filled": 0,
                    "orders_failed": 0,
                    "orders_hedged": 0,
                    "hedge_spread_pnl": 0,
                    "taker_fee": 0,
                    "maker_fee": 0,
                }

            # Sleep for a certain amount of time
            await asyncio.sleep(
                self.settings["performance_tracking_interval"]
            )  # sleep for 60 seconds
