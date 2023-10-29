"""Support for WundaSmart."""
from __future__ import annotations

from datetime import timedelta
import asyncio
import logging
from typing import Final

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_HOST, CONF_PASSWORD, CONF_USERNAME, Platform
from homeassistant.core import HomeAssistant
from homeassistant.helpers import aiohttp_client
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import DOMAIN
from .pywundasmart import get_devices

_LOGGER = logging.getLogger(__name__)

PLATFORMS: Final[list[Platform]] = [
    Platform.CLIMATE,
    Platform.WATER_HEATER
]

async def async_setup(hass: HomeAssistant, config):
    "Setting up this integration using YAML is not supported."
    return True

async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up WundaSmart from a config entry."""
    hass.data.setdefault(DOMAIN, {})
    wunda_ip = entry.data[CONF_HOST]
    wunda_user = entry.data[CONF_USERNAME]
    wunda_pass = entry.data[CONF_PASSWORD]

    coordinator = WundasmartDataUpdateCoordinator(
        hass, wunda_ip, wunda_user, wunda_pass
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

    def __init__(self, hass, wunda_ip, wunda_user, wunda_pass):
        """Initialize."""
        self._hass = hass
        self._wunda_ip = wunda_ip
        self._wunda_user = wunda_user
        self._wunda_pass = wunda_pass
        self._devices = {}

        update_interval = timedelta(minutes=1)
        super().__init__(hass, _LOGGER, name=DOMAIN, update_interval=update_interval)

    async def _async_update_data(self):
        attempts = 0
        while attempts < 3:
            attempts += 1

            result = await get_devices(
                aiohttp_client.async_get_clientsession(self._hass),
                self._wunda_ip,
                self._wunda_user,
                self._wunda_pass,
            )

            if result["state"]:
                for wunda_id, device in result["devices"].items():
                    state = device.get("state")
                    if state is not None:
                        prev = self._devices.setdefault(wunda_id, {})
                        self._devices[wunda_id] |= device | {
                            "state": prev.get("state", {}) | state
                        }

                return self._devices

            if attempts < 3:
                _LOGGER.warning(f"Failed to fetch state information from Wundasmart (will retry): {result=}")
                await asyncio.sleep(0.1)

        _LOGGER.warning(f"Failed to fetch state information from Wundasmart: {result=}")
        raise UpdateFailed()
