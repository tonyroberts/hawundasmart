"""Support for WundaSmart."""
from __future__ import annotations

from datetime import timedelta
import logging
from typing import Final

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_HOST, Platform
from homeassistant.core import HomeAssistant
from homeassistant.helpers import aiohttp_client
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .const import DOMAIN
from pywundasmart import get_devices, get_states

_LOGGER = logging.getLogger(__name__)

PLATFORMS: Final[list[Platform]] = [
    Platform.CLIMATE,
]

async def async_setup(hass: HomeAssistant, config: Config):
    "Setting up this integration using YAML is not supported."
    return True

async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up WundaSmart from a config entry."""
    hass.data.setdefault(DOMAIN, {})
    wunda_ip = entry.data[CONF_HOST]
    wunda_user = 'root'
    wunda_pass = 'root'

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
        self._devices = None

        update_interval = timedelta(minutes=1)
        super().__init__(hass, _LOGGER, name=DOMAIN, update_interval=update_interval)

    async def _async_update_data(self):
        if self._devices is None:
            result = await get_devices(
                aiohttp_client.async_get_clientsession(self._hass),
                self._wunda_ip,
                self._wunda_user,
                self._wunda_pass,
            )
            if result["state"]:
                self._devices = result["devices"]
            else:
                raise UpdateFailed()

        result = await get_states(
            aiohttp_client.async_get_clientsession(self._hass),
            self._wunda_ip,
            self._wunda_user,
            self._wunda_pass,
        )

        for device in self._devices:
            dev = next(
                (dev for dev in result if dev["sn"] == device["sn"]),
                None,
            )
            if dev is not None and "state" in dev:
                device["state"] = dev["state"]
        return self._devices
