ETH = {
    "name": "ETH-Perp",
    "marginShare": 0.33,
    "leverage": 5,
    "refreshTolerance": 0.03,
    "orderExpiry": 2,
    "defensiveSkew": 0.01,
    "priceFeed": "binance-futures",
    "avoidCrossing": True,
    "orderLevels": {
        "1": {"spread": 0.01, "qty": 0.12, "refreshTolerance": 0},
        "2": {"spread": 0.03, "qty": 0.23, "refreshTolerance": 0},
        "3": {"spread": 0.05, "qty": 0.45, "refreshTolerance": 0},
    },
    "hedge": "hyperliquid",
}

AVAX = {
    "name": "AVAX-Perp",
    "marginShare": 1,
    "leverage": 2,
    "refreshTolerance": 0.03,  # unused
    "orderFrequency": 2,  # create new orders at this frequency
    "orderExpiry": 2,  # orders expire after this time
    "defensiveSkew": 0,  # Add a multiple of this to the spread when position skews in one side. Can be 0 with hedge mode
    "priceFeed": "binance-futures",
    "avoidCrossing": False,
    "orderLevels": {
        "1": {"spread": 0.01, "qty": 3, "refreshTolerance": 0},
        "2": {"spread": 0.02, "qty": 4, "refreshTolerance": 0},
        "3": {"spread": 0.03, "qty": 4, "refreshTolerance": 0},
    },
    "hedge": "hyperliquid",  # binance/hyperliquid. binance is not implemented yet
    "hedgeMode": True,  # enable hedge mode ?
    "slippage": 0.01,  # max slippage for hegde orders
    "futures_feed_frequency": 1,  # binance feed frequency to get mid price for generating new orders with configured spread around this mid price.
    "mid_price_expiry": 2,  # expiry of mid price from price feed while generating new orders (Should be greater than binance feed frequency)
    "hedgeClient_orderbook_frequency": 5,  # binance/hyperliquid feed frequency
    "hedgeClient_user_state_frequency": 5,  # binance/hyperliquid feed frequency
    "orderFillCooldown": 20,  # wait these many seconds before placing another order after one is filled.
    "hubblePositionPollInterval": 5,  # poll hubble for position data every x seconds
    "position_data_expiry": 10,  # expiry of position data for hubble positions (should be greater than hubblePositionPollInterval)
    "hubble_orderbook_frequency": "500ms",  # update Hubble orderbook at this freq
    "performance_tracking_interval": 120,  # track performance every x seconds as a new row in the csv
}

SOL = {
    "name": "SOL-Perp",
    "marginShare": 0.33,
    "leverage": 5,
    "refreshTolerance": 0.03,
    "orderExpiry": 2,
    "defensiveSkew": 0.01,
    "priceFeed": "binance-futures",
    "avoidCrossing": True,
    "orderLevels": {
        "1": {"spread": 0.01, "qty": 3.1, "refreshTolerance": 0},
        "2": {"spread": 0.02, "qty": 4.2, "refreshTolerance": 0},
        "3": {"spread": 0.03, "qty": 5.3, "refreshTolerance": 0},
    },
    "hedge": "hyperliquid",
}
