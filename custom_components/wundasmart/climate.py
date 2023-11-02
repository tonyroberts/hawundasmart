"""Support for WundaSmart climate."""
from __future__ import annotations

import math
import logging
from typing import Any

from aiohttp.client import ClientSession, BasicAuth

from homeassistant.components.climate import (
    ATTR_HVAC_MODE,
    ClimateEntity,
    ClimateEntityFeature,
    HVACAction,
    HVACMode,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import (
    ATTR_TEMPERATURE,
    CONF_HOST,
    CONF_USERNAME,
    CONF_PASSWORD,
    TEMP_CELSIUS,
)
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers import aiohttp_client
from homeassistant.helpers.entity import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from . import WundasmartDataUpdateCoordinator
from .pywundasmart import send_command
from .const import DOMAIN

_LOGGER = logging.getLogger(__name__)

SUPPORTED_HVAC_MODES = [
    HVACMode.OFF,
    HVACMode.AUTO,
    HVACMode.HEAT,
]

PARALLEL_UPDATES = 1

async def async_setup_entry(
    hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback
) -> None:
    """Set up Wundasmart climate."""
    wunda_ip: str = entry.data[CONF_HOST]
    wunda_user: str = entry.data[CONF_USERNAME]
    wunda_pass: str = entry.data[CONF_PASSWORD]
    coordinator: WundasmartDataUpdateCoordinator = hass.data[DOMAIN][entry.entry_id]
    async_add_entities(
        Device(
            hass,
            wunda_ip,
            wunda_user,
            wunda_pass,
            wunda_id,
            device,
            coordinator,
        )
        for wunda_id, device in coordinator.data.items() if device.get("device_type") == "ROOM" and "name" in device
    )


class Device(CoordinatorEntity[WundasmartDataUpdateCoordinator], ClimateEntity):
    """Representation of an Wundasmart climate."""

    _attr_hvac_modes = SUPPORTED_HVAC_MODES
    _attr_temperature_unit = TEMP_CELSIUS

    def __init__(
        self,
        hass: HomeAssistant,
        wunda_ip: str,
        wunda_user: str,
        wunda_pass: str,
        wunda_id: str,
        device: dict[str, Any],
        coordinator: WundasmartDataUpdateCoordinator,
    ) -> None:
        """Initialize the Wundasmart climate."""
        super().__init__(coordinator)
        self._hass = hass
        self._wunda_ip = wunda_ip
        self._wunda_user = wunda_user
        self._wunda_pass = wunda_pass
        self._wunda_id = wunda_id
        self._attr_name = device["name"].replace("%20", " ")
        self._attr_unique_id = device["id"]
        self._attr_type = device["device_type"]
        self._attr_device_info = DeviceInfo(
            identifiers={
                (DOMAIN, device["id"]),
            },
            manufacturer="WundaSmart",
            name=self.name.replace("%20", " "),
            model=device["device_type"]
        )
        self._attr_supported_features = ClimateEntityFeature.TARGET_TEMPERATURE
        self._attr_current_temperature = 0
        self._attr_target_temperature = 0
        self._attr_current_humidity = 0
        self._attr_hvac_mode = HVACMode.AUTO

    @callback
    def _handle_coordinator_update(self) -> None:
        """Handle updated data from the coordinator."""
        device = self.coordinator.data.get(self._wunda_id)
        if device is not None and "state" in device and device.get("device_type") == "ROOM":
            state = device["state"]
            if state.get("t") is not None:
                try:
                    self._attr_current_temperature = float(state["t"])
                except (ValueError, TypeError):
                    _LOGGER.warning(f"Unexpected temperature value '{state['t']}' for {self._attr_name}")

            if state.get("h") is not None:
                try:
                    self._attr_current_humidity = float(state["h"])
                except (ValueError, TypeError):
                    _LOGGER.warning(f"Unexpected humidity value '{state['h']}' for {self._attr_name}")

            if state.get("sp") is not None:
                try:
                    self._attr_target_temperature = float(state["sp"])
                except (ValueError, TypeError):
                    _LOGGER.warning(f"Unexpected set point value '{state['sp']}' for {self._attr_name}")

            if state.get("tp") is not None:
                try:
                    # tp appears to be the following flags:
                    # - 00000001 (0x01) indicates a manual override is set until the next manual override
                    # - 00000100 (0x04) indicates the set point temperature has been set to 'off'
                    # - 00010000 (0x10) indicates a manual override has been set
                    # - 00100000 (0x20) indicates heating demand
                    # - 10000000 (0x80) indicates the adaptive start mode is active
                    flags = int(state["tp"])
                    self._attr_hvac_mode = HVACMode.HEAT if (flags & (0x10 | 0x80)) == 0x10 else HVACMode.AUTO
                    self._attr_hvac_action = (
                        HVACAction.PREHEATING if ((flags & (0x80 | 0x20)) == (0x80 | 0x20))
                        else HVACAction.HEATING if flags & 0x20 
                        else HVACAction.OFF
                    )
                except (ValueError, TypeError):
                    _LOGGER.warning(f"Unexpected 'tp' value '{state['tp']}' for {self._attr_name}")

        super()._handle_coordinator_update()

    async def async_added_to_hass(self) -> None:
        """When entity is added to hass."""
        await super().async_added_to_hass()
        self._handle_coordinator_update()

    async def async_set_temperature(self, temperature, **kwargs):
        # Set the new target temperature
        session = aiohttp_client.async_create_clientsession(self._hass)
        await send_command(session, self._wunda_ip, self._wunda_user, self._wunda_pass, params={
            "cmd": 1,
            "roomid": self._wunda_id,
            "temp": temperature,
            "locktt": 0,
            "time": 0
        })

        # Fetch the updated state
        await self.coordinator.async_request_refresh()

    async def async_set_hvac_mode(self, hvac_mode: HVACMode):
        if hvac_mode == HVACMode.AUTO:
            # Set to programmed mode
            session = aiohttp_client.async_create_clientsession(self._hass)
            await send_command(session, self._wunda_ip, self._wunda_user, self._wunda_pass, params={
                "cmd": 1,
                "roomid": self._wunda_id,
                "prog": None,
                "locktt": 0,
                "time": 0
            })
        elif hvac_mode == HVACMode.HEAT:
            # Set the target temperature to the current temperature + 1 degree, rounded up
            session = aiohttp_client.async_create_clientsession(self._hass)
            await send_command(session, self._wunda_ip, self._wunda_user, self._wunda_pass, params={
                "cmd": 1,
                "roomid": self._wunda_id,
                "temp": math.ceil(self._attr_current_temperature) + 1,
                "locktt": 0,
                "time": 0
            })
        elif hvac_mode == HVACMode.OFF:
            # Set the target temperature to zero
            session = aiohttp_client.async_create_clientsession(self._hass)
            await send_command(session, self._wunda_ip, self._wunda_user, self._wunda_pass, params={
                "cmd": 1,
                "roomid": self._wunda_id,
                "temp": 0.0,
                "locktt": 0,
                "time": 0
            })
        else:
            raise NotImplementedError(f"Unsupported HVAC mode {hvac_mode}")

        # Fetch the updated state
        await self.coordinator.async_request_refresh()
