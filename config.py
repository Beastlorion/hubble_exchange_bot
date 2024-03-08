ETH = {
    "name": "ETH-Perp",
    "marginShare": 0.33,
    "leverage": 5,
    "refreshTolerance": 0.03,
    "refreshInterval": 0.1,
    "defensiveSkew": 0.01,
    "priceFeed": "binance-futures",
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
    "refreshInterval": 2,
    "defensiveSkew": 0.01,
    "priceFeed": "binance-spot",
    "orderLevels": {
        "1": {
            "spread": 0.02,
            "qty": 3,
            "refreshTolerance": 0
        }
    }
}

SOL = {
    "name": "SOL-Perp",
    "marginShare": 0.33,
    "leverage": 5,
    "refreshTolerance": 0.03,
    "refreshInterval": 0.1,
    "defensiveSkew": 0.01,
    "priceFeed": "binance-futures",
    "orderLevels": {
        "1": {
            "spread": 0.05,
            "qty": 1.2,
            "refreshTolerance": 0
        }
    }
}