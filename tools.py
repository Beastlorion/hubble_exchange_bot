def get_key(d, v):
    for key, item in d.items():
        if item == v:
            return key


def get_symbol_from_name(market):
    return market.split("-")[0]


async def generic_callback(response):
    # print(f"Received response: {response}")
    return response
