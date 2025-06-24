import asyncio
import functools

def async_retry(retries=3, delay=1, exceptions=(Exception,)):
    def decorator(func):
        @functools.wraps(func)
        async def wrapper(*args, **kwargs):
            for attempt in range(retries):
                try:
                    return await func(*args, **kwargs)
                except exceptions as e:
                    if attempt == retries - 1:
                        raise
                    await asyncio.sleep(delay)
        return wrapper
    return decorator

async def run_with_timeout(coro, timeout):
    return await asyncio.wait_for(coro, timeout) 