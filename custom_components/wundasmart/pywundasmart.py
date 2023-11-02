import asyncio
import aiohttp
import logging
import json

_LOGGER = logging.getLogger(__name__)


DEVICE_DEFS = {'device_sn', 'prod_sn', 'device_name', 'device_type', 'eth_mac', 'name', 'id', 'i'}


async def get_devices(httpsession: aiohttp.ClientSession, wunda_ip, wunda_user, wunda_pass):
    """ Returns a list of active devices connected to the Wundasmart controller """

    devices = {}

    # Query the cmd API, which returns a list of rooms configured on the controller. Data is formatted in JSON
    wunda_url = f"http://{wunda_ip}/cmd.cgi"
    try:
        async with httpsession.get(wunda_url, auth=aiohttp.BasicAuth(wunda_user, wunda_pass)) as resp:
            status = resp.status

            if status == 200:
                data = await resp.json()
                for room in data["rooms"]:
                    room_id = str(room["i"])
                    device = devices.setdefault(room_id, {"device_type": "ROOM"})
                    state = device.setdefault("state", {})
                    device.update({k: v for k, v in room.items() if k in DEVICE_DEFS})
                    state.update({k: v for k, v in room.items() if k not in DEVICE_DEFS})
            else:
                _LOGGER.warning(f"Error getting cmd.cgi: {resp}")
                return {"state": False, "code": status}
    except (asyncio.TimeoutError, aiohttp.ClientError):
        _LOGGER.warning("Error getting cmd.cgi", exc_info=True)
        return {"state": False, "code": 500}

    # Query the syncvalues API, which returns a list of all sensor values for all devices. Data is formatted as semicolon-separated k;v pairs
    wunda_url = f"http://{wunda_ip}/syncvalues.cgi?v=2"
    try:
        async with httpsession.get(wunda_url, auth=aiohttp.BasicAuth(wunda_user, wunda_pass)) as resp:
            status = resp.status
            if status == 200:
                data = await resp.text()
                for device_state in data.splitlines():
                    device_values = dict(x.split(":") for x in device_state.split(";") if ":" in x)
                    device_id = str(device_state.split(";")[0])

                    device = devices.setdefault(device_id, {})
                    state = device.setdefault("state", {})

                    device.update({k: v for k, v in device_values.items() if k in DEVICE_DEFS})
                    state.update({k: v for k, v in device_values.items() if k not in DEVICE_DEFS})
            else:
                _LOGGER.warning(f"Error getting syncvalues.cgi: {resp}")
                return {"state": False, "code": status}
    except (asyncio.TimeoutError, aiohttp.ClientError):
        _LOGGER.warning("Error getting syncvalues.cgi", exc_info=True)
        return {"state": False, "code": 500, "message": "HTTP client error"}

    # Give each device a unique id based on wunda id and device type
    for device_id, device in devices.items():
        device_type = device.get("device_type", "unknown")
        device["id"] = f"{device_type}.{device_id}"

    return {"state": True, "devices": devices}


async def send_command(session: aiohttp.ClientSession, 
                       wunda_ip: str,
                       wunda_user: str, 
                       wunda_pass: str,
                       params: dict,
                       retries: int = 3,
                       retry_delay: float = 0.1):
    """Send a command to the wunda smart hub controller"""
    wunda_url = f"http://{wunda_ip}/cmd.cgi"
    params = "&".join((k if v is None else f"{k}={v}"for k, v in params.items()))

    attempts = 0
    while attempts < retries:
        attempts += 1

        async with session.get(wunda_url, auth=aiohttp.BasicAuth(wunda_user, wunda_pass), params=params) as resp:
            status = resp.status
            if status == 200:
                return json.loads(await resp.text())

        if attempts < retries:
            _LOGGER.warning(f"Failed to send command to Wundasmart (will retry): {status=}")
            await asyncio.sleep(retry_delay)

    _LOGGER.warning(f"Failed to send command to Wundasmart : {status=}")
    raise RuntimeError(f"Failed to send command: {params=}; {status=}")
