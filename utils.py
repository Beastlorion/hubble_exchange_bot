import asyncio
import logging
import sys
logger = logging.getLogger()
logger.setLevel(logging.INFO)
import time
from functools import wraps

logHandler = logging.StreamHandler(sys.stdout)
logHandler.setLevel(logging.INFO)
logHandler.setFormatter(logging.Formatter('%(asctime)s: %(message)s'))
logger.addHandler(logHandler)

errLogHandler = logging.StreamHandler(sys.stderr)
errLogHandler.setLevel(logging.ERROR)
errLogHandler.setFormatter(logging.Formatter('%(asctime)s: %(message)s'))
logger.addHandler(errLogHandler)



def timeit(method):
    @wraps(method)
    async def timed_async(*args, **kw):
        start_time = time.time()
        result = await method(*args, **kw)
        end_time = time.time()
        logger.info(f"Async method {method.__qualname__} took {end_time - start_time:.6f} seconds")
        return result

    def timed_sync(*args, **kw):
        start_time = time.time()
        result = method(*args, **kw)
        end_time = time.time()
        logger.info(f"Sync method {method.__qualname__} took {end_time - start_time:.6f} seconds")
        return result

    if asyncio.iscoroutinefunction(method):
        return timed_async
    else:
        return timed_sync

def get_logger():
    return logger


def with_slippage(price, slippage, is_buy):
    price *= (1 + slippage) if is_buy else (1 - slippage)
        # We round px to 5 significant figures and 6 decimals
    return round(float(price), 3)

