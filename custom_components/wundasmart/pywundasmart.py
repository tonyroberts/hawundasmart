from .const import *
import asyncio
import aiohttp
import logging
import warnings
import json
import math

_LOGGER = logging.getLogger(__name__)


DEVICE_DEFS = {'device_sn', 'prod_sn', 'device_name', 'device_type', 'eth_mac', 'name', 'id', 'i'}


def get_device_id_ranges(hw_version: float):
    id_ranges = DEVICE_ID_RANGES.get(int(math.floor(hw_version)))
    if id_ranges:
        return id_ranges

    # Default to HW version 4 if there's no explicit config for this version.
    warnings.warn(f"Unknown HW version '{hw_version}'. Raise a github issue if you experience problems.")
    return DEVICE_ID_RANGES[4]


def _device_type_from_id(device_id: int, hw_version: float) -> str:
    """Infer the device type from the wunda id"""
    id_ranges = get_device_id_ranges(hw_version)
    if device_id < id_ranges.MIN_SENSOR_ID:
        return "wunda"  # hub switch
    if id_ranges.MIN_SENSOR_ID <= device_id <= id_ranges.MAX_SENSOR_ID:
        return"SENSOR"  # thermostats and humidity sensors
    if id_ranges.MIN_TRV_ID <= device_id <= id_ranges.MAX_TRV_ID:
        return "TRV"  # radiator valves
    if id_ranges.MIN_UFH_ID <= device_id <= id_ranges.MAX_UFH_ID:
        return "UFH"  # underfloor heating connection box
    if id_ranges.MIN_ROOM_ID <= device_id <= id_ranges.MAX_ROOM_ID:
        return "ROOM"
    return "UNKNOWN"


def get_sensor_id_from_room(device) -> int:
    """Infer the sensor id from a room device"""
    device_id = int(device["device_id"])
    hw_version = float(device["hw_version"])
    id_ranges = get_device_id_ranges(hw_version)
    return device_id - id_ranges.MIN_ROOM_ID + id_ranges.MIN_SENSOR_ID


def get_room_id_from_device(device) -> int:
    """Infer the room id from a sensor device"""
    device_type = device["device_type"]
    device_id = int(device["device_id"])
    hw_version = float(device["hw_version"])
    id_ranges = get_device_id_ranges(hw_version)

    match(device_type):
        case "SENSOR":
            return device_id - id_ranges.MIN_SENSOR_ID + id_ranges.MIN_ROOM_ID
        case "TRV":
            room_id = device.get("state", {}).get("room_id")
            if room_id is None:
                return None
            return int(room_id) + id_ranges.MIN_ROOM_ID
        case "ROOM":
            return device_id

    raise RuntimeError(f"Device type '{device_type}' has no room")


def parse_syncvalues(data: str):
    """Parses the result from syncvalues.cgi.

    Returns a dictionary of devices, keyed by device id.
    """
    devices = {}
    device_sn = None
    hw_version = 0
    for device_state in data.splitlines():
        raw_values = device_state.split(";")
        device_values = dict(x.split(":") for x in raw_values if ":" in x)

        # This is set once for the first item and is the hub switch serial number
        device_sn = device_sn or device_values.get("device_sn")
        if device_sn is None:
            raise RuntimeError("No device_sn found")

        hw_version = hw_version or float(device_values.get("device_hard_version", 0.0))
        if not hw_version:
            raise RuntimeError("No device_hard_version found")

        # The second number is zero for unused entities
        if 0 == int(raw_values[1]):
            continue

        device_id = int(raw_values[0])
        device_type = _device_type_from_id(device_id, hw_version)

        # Rooms have 'enable' set to 255 when not set up
        if device_type == "ROOM" and device_values.get("enable") == "255":
            continue

        device = devices.setdefault(device_id, {
            "device_type": device_type,
            "device_id": device_id,
            "hw_version": hw_version
        })

        state = device.setdefault("state", {})

        device.update({k: v for k, v in device_values.items() if k in DEVICE_DEFS})
        state.update({k: v for k, v in device_values.items() if k not in DEVICE_DEFS})

        # Give each device a unique id based on the hub switch serial number and device id
        device["id"] = f"wunda.{device_sn}.{device_id}"

        # Add the sensor values to the rooms
        if device_type == "ROOM":
            sensor_id = get_sensor_id_from_room(device)
            sensor = devices.get(sensor_id, {})
            device["sensor_state"] = sensor.get("state", {})

    return devices


async def get_devices(httpsession: aiohttp.ClientSession, wunda_ip, wunda_user, wunda_pass, timeout=10):
    """ Returns a list of active devices connected to the Wundasmart controller """
    # Query the syncvalues API, which returns a list of all sensor values for all devices. Data is formatted as semicolon-separated k;v pairs
    wunda_url = f"http://{wunda_ip}/syncvalues.cgi"
    try:
        async with httpsession.get(wunda_url,
                                   auth=aiohttp.BasicAuth(wunda_user, wunda_pass),
                                   timeout=timeout) as resp:
            status = resp.status
            if status == 200:
                data = await resp.text()
                devices = parse_syncvalues(data)
                return {"state": True, "devices": devices}
            else:
                _LOGGER.warning(f"Error getting syncvalues.cgi: {resp}")
                return {"state": False, "code": status}
    except (asyncio.TimeoutError, aiohttp.ClientError):
        _LOGGER.warning("Error getting syncvalues.cgi", exc_info=True)
        return {"state": False, "code": 500, "message": "HTTP client error"}


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
        async with session.get(wunda_url,
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
