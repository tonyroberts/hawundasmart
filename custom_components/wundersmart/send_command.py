from aiohttp import BasicAuth, ClientSession
import logging
import asyncio
import json

_LOGGER = logging.getLogger(__name__)


async def send_command(session: ClientSession, wunda_ip: str, wunda_user: str, wunda_pass: str, params: dict):
    """Send a command to the wunda smart hub controller"""
    wunda_url = f"http://{wunda_ip}/cmd.cgi"
    params = "&".join((k if v is None else f"{k}={v}"for k, v in params.items()))

    attempts = 0
    while attempts < 3:
        attempts += 1

        resp = await session.get(wunda_url, auth=BasicAuth(wunda_user, wunda_pass), params=params)
        status = resp.status
        if status == 200:
            return json.loads(await resp.text())

        if attempts < 3:
            _LOGGER.warning(f"Failed to send command to Wundasmart (will retry): {status=}")
            await asyncio.sleep(0.1)

    _LOGGER.warning(f"Failed to send command to Wundasmart : {status=}")
    raise RuntimeError(f"Failed to send command: {params=}; {status=}")
