from .const import *
import asyncio
import aiohttp
import logging
import json

_LOGGER = logging.getLogger(__name__)


DEVICE_DEFS = {'device_sn', 'prod_sn', 'device_name', 'device_type', 'eth_mac', 'name', 'id', 'i'}

_semaphores = {}

def _get_semaphore(wunda_ip):
    """Return a semaphore object to restrict making concurrent requests to the Wundasmart hub switch."""
    semaphore = _semaphores.get(wunda_ip)
    if semaphore is None:
        semaphore = asyncio.Semaphore(value=1)
        _semaphores[wunda_ip] = semaphore
    return semaphore


def _device_type_from_id(device_id: int) -> str:
    """Infer the device type from the wunda id"""
    if device_id < MIN_SENSOR_ID:
        return "wunda"  # hub switch
    if MIN_SENSOR_ID <= device_id <= MAX_SENSOR_ID:
        return"SENSOR"  # thermostats and humidity sensors
    if MIN_TRV_ID <= device_id <= MAX_TRV_ID:
        return "TRV"  # radiator valves
    if MIN_UFH_ID <= device_id <= MAX_UFH_ID:
        return "UFH"  # underfloor heating connection box
    if MIN_ROOM_ID <= device_id <= MAX_ROOM_ID:
        return "ROOM"
    return "UNKNOWN"


async def get_devices(httpsession: aiohttp.ClientSession, wunda_ip, wunda_user, wunda_pass, timeout=10):
    """ Returns a list of active devices connected to the Wundasmart controller """
    devices = {}

    # Query the syncvalues API, which returns a list of all sensor values for all devices. Data is formatted as semicolon-separated k;v pairs
    wunda_url = f"http://{wunda_ip}/syncvalues.cgi"
    try:
        async with _get_semaphore(wunda_ip), \
                httpsession.get(wunda_url,
                                auth=aiohttp.BasicAuth(wunda_user, wunda_pass),
                                timeout=timeout) as resp:
            status = resp.status
            if status == 200:
                data = await resp.text()
                device_sn = None
                for device_state in data.splitlines():
                    device_values = dict(x.split(":") for x in device_state.split(";") if ":" in x)
                    device_id = int(device_state.split(";")[0])
                    device_type = _device_type_from_id(device_id)

                    # This is set once for the first item and is the hub switch serial number
                    device_sn = device_sn or device_values.get("device_sn")
                    if device_sn is None:
                        raise RuntimeError("No device_sn found")

                    device = devices.setdefault(device_id, {"device_type": device_type})
                    state = device.setdefault("state", {})

                    device.update({k: v for k, v in device_values.items() if k in DEVICE_DEFS})
                    state.update({k: v for k, v in device_values.items() if k not in DEVICE_DEFS})

                    # Give each device a unique id based on the hub switch serial number and device id
                    device["id"] = f"wunda.{device_sn}.{device_id}"

                    # Add the sensor values to the rooms
                    if device_type == "ROOM":
                        sensor_id = device_id - MIN_ROOM_ID + MIN_SENSOR_ID
                        sensor = devices.get(sensor_id, {})
                        device["sensor_state"] = sensor.get("state", {})
            else:
                _LOGGER.warning(f"Error getting syncvalues.cgi: {resp}")
                return {"state": False, "code": status}
    except (asyncio.TimeoutError, aiohttp.ClientError):
        _LOGGER.warning("Error getting syncvalues.cgi", exc_info=True)
        return {"state": False, "code": 500, "message": "HTTP client error"}

    return {"state": True, "devices": devices}


async def send_command(session: aiohttp.ClientSession, 
                       wunda_ip: str,
                       wunda_user: str, 
                       wunda_pass: str,
                       params: dict,
                       timeout: int = 3,
                       retries: int = 5,
                       retry_delay: float = 0.5):
    """Send a command to the wunda smart hub controller"""
    wunda_url = f"http://{wunda_ip}/cmd.cgi"
    params = "&".join((k if v is None else f"{k}={v}"for k, v in params.items()))

    attempts = 0
    while attempts < retries:
        attempts += 1

        async with _get_semaphore(wunda_ip), \
                session.get(wunda_url,
                            auth=aiohttp.BasicAuth(wunda_user, wunda_pass), 
                            params=params,
                            timeout=timeout) as resp:
            status = resp.status
            if status == 200:
                return json.loads(await resp.text())

        if attempts < retries:
            _LOGGER.warning(f"Failed to send command to Wundasmart (will retry): {status=}")
            await asyncio.sleep(retry_delay)

    _LOGGER.warning(f"Failed to send command to Wundasmart : {status=}")
    raise RuntimeError(f"Failed to send command: {params=}; {status=}")
