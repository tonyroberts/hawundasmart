"""Support for WundaSmart."""
from __future__ import annotations

from datetime import timedelta
import asyncio
import aiohttp
import logging
from typing import Final
from contextlib import AbstractAsyncContextManager

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_HOST, CONF_PASSWORD, CONF_USERNAME, CONF_SCAN_INTERVAL, Platform
from homeassistant.core import HomeAssistant
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed
from homeassistant.helpers.device_registry import DeviceInfo

from .const import *
from .session import get_persistent_session
from .pywundasmart import get_devices

_LOGGER = logging.getLogger(__name__)

PLATFORMS: Final[list[Platform]] = [
    Platform.CLIMATE,
    Platform.WATER_HEATER,
    Platform.SENSOR,
    Platform.BINARY_SENSOR
]


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up WundaSmart from a config entry."""
    hass.data.setdefault(DOMAIN, {})
    wunda_ip = entry.data[CONF_HOST]
    wunda_user = entry.data[CONF_USERNAME]
    wunda_pass = entry.data[CONF_PASSWORD]
    update_interval = entry.options.get(CONF_SCAN_INTERVAL, DEFAULT_SCAN_INTERVAL)
    connect_timeout = entry.options.get(CONF_CONNECT_TIMEOUT, DEFAULT_CONNECT_TIMEOUT)
    read_timeout = entry.options.get(CONF_READ_TIMEOUT, DEFAULT_READ_TIMEOUT)
    timeout = aiohttp.ClientTimeout(sock_connect=connect_timeout, sock_read=read_timeout)

    coordinator = WundasmartDataUpdateCoordinator(
        hass, wunda_ip, wunda_user, wunda_pass, update_interval, timeout
    )
    await coordinator.async_config_entry_first_refresh()

    entry.async_on_unload(entry.add_update_listener(update_listener))

    hass.data[DOMAIN][entry.entry_id] = coordinator

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)

    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload a config entry."""
    unload_ok = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    if unload_ok:
        hass.data[DOMAIN].pop(entry.entry_id)

    return unload_ok


async def async_reload_entry(hass: HomeAssistant, entry: ConfigEntry) -> None:
    """Reload config entry."""
    await async_unload_entry(hass, entry)
    await async_setup_entry(hass, entry)


async def update_listener(hass: HomeAssistant, config_entry: ConfigEntry) -> None:
    """Update listener."""
    await hass.config_entries.async_reload(config_entry.entry_id)


class WundasmartDataUpdateCoordinator(DataUpdateCoordinator):
    """Class to manage fetching data from WundaSmart API."""

    def __init__(self,
                 hass: HomeAssistant,
                 wunda_ip: str,
                 wunda_user: str,
                 wunda_pass: str,
                 update_interval: int,
                 timeout: aiohttp.ClientTimeout):
        """Initialize."""
        self._hass = hass
        self._wunda_ip = wunda_ip
        self._wunda_user = wunda_user
        self._wunda_pass = wunda_pass
        self._devices = {}
        self._device_sn = None
        self._device_name = None
        self._sw_version = None
        self._hw_version = None
        self._timeout = timeout
        self._keepalive_timeout = update_interval * 2

        super().__init__(hass,
                         _LOGGER,
                         name=DOMAIN,
                         update_interval=timedelta(seconds=update_interval))

    async def _async_update_data(self):
        attempts = 0
        max_attempts = 5
        while attempts < max_attempts:
            attempts += 1

            async with self.get_session() as session:
                result = await get_devices(
                    session,
                    self._wunda_ip,
                    self._wunda_user,
                    self._wunda_pass,
                    timeout=self._timeout
                )

            if result["state"]:
                break

            if attempts < max_attempts:
                _LOGGER.warning(f"Failed to fetch state information from Wundasmart (will retry): {result=}")
                await asyncio.sleep(1)
        else:
            _LOGGER.warning(f"Failed to fetch state information from Wundasmart: {result=}")
            raise UpdateFailed()

        for wunda_id, device in result["devices"].items():
            state = device.get("state")
            if state is not None:
                prev = self._devices.setdefault(wunda_id, {})
                self._devices[wunda_id] |= device | {
                    "state": prev.get("state", {}) | state
                }

            sensor_state = device.get("sensor_state")
            if sensor_state is not None:
                prev = self._devices.setdefault(wunda_id, {})
                self._devices[wunda_id] |= device | {
                    "sensor_state": prev.get("sensor_state", {}) | sensor_state
                }

            # Get the hub switch serial number if we don't have it already
            if self._device_sn is None and "device_sn" in device:
                self._device_sn = device["device_sn"]
                self._device_name = device.get("name", "Smart HubSwitch")
                self._sw_version = device.get("device_soft_version", "unknown")
                self._hw_version = device.get("device_hard_version", "unknown")

        return self._devices

    def get_session(self) -> AbstractAsyncContextManager:
        """Context manager for getting aiohttp session for any request made to the Wunda hub."""
        return get_persistent_session(wunda_ip=self._wunda_ip, keepalive_timeout=self._keepalive_timeout)

    @property
    def device_sn(self):
        return self._device_sn

    @property
    def device_info(self) -> DeviceInfo | None:
        """Return device info for the hub device."""
        if self._device_sn is None:
            return None

        return DeviceInfo(
            identifiers={(DOMAIN, self._device_sn)},
            manufacturer="Wunda",
            name=self._device_name or "Smart HubSwitch",
            model="WundaSmart Hub",
            hw_version=self._hw_version,
            sw_version=self._sw_version
        )

    def get_room_device_info(self, room_id: str, room_device: dict) -> DeviceInfo | None:
        """Return device info for a room/zone."""
        if self._device_sn is None:
            return None

        room_name = room_device.get("name", f"Room {room_id}")
        
        return DeviceInfo(
            identifiers={(DOMAIN, f"{self._device_sn}_room_{room_id}")},
            manufacturer="Wunda",
            name=room_name,
            model="WundaSmart Room",
            via_device=(DOMAIN, self._device_sn),
        )
