from contextlib import asynccontextmanager
import aiohttp
import asyncio


@asynccontextmanager
async def get_session():
    connector = aiohttp.TCPConnector(force_close=True, limit=1)
    try:
        async with aiohttp.ClientSession(connector=connector) as session:
            yield session
    finally:
        await connector.close()
        # Zero-sleep to allow underlying connections to close
        # https://docs.aiohttp.org/en/stable/client_advanced.html#graceful-shutdown
        await asyncio.sleep(0)
