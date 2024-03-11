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
        "1": {
            "spread": 0.05,
            "qty": 0.05,
            "refreshTolerance": 0
        }
    }
}

AVAX = {
    "name": "AVAX-Perp",
    "marginShare": 1,
    "leverage": 2,
    "refreshTolerance": 0.03,
    "orderExpiry": 2,
    "defensiveSkew": 0.01,
    "priceFeed": "binance-futures",
    "avoidCrossing": True,
    "orderLevels": {
        "1": {
            "spread": 0.003,
            "qty": 6,
            "refreshTolerance": 0
        },
        # "2": {
        #     "spread": 0.005,
        #     "qty": 1,
        #     "refreshTolerance": 0
        # }
    }
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
        "1": {
            "spread": 0.05,
            "qty": 1.2,
            "refreshTolerance": 0
        }
    }
}