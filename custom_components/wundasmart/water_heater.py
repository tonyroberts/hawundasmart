"""Support for WundaSmart water heater."""
from __future__ import annotations

import logging
import math
from typing import Any
from datetime import timedelta

from homeassistant.components.water_heater import (
    WaterHeaterEntity,
    WaterHeaterEntityFeature
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import (
    CONF_HOST,
    CONF_USERNAME,
    CONF_PASSWORD,
    STATE_ON,
    STATE_OFF,
    UnitOfTemperature,
)
from homeassistant.core import HomeAssistant, ServiceCall, callback
from homeassistant.helpers import aiohttp_client, entity_platform
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity
import homeassistant.helpers.config_validation as cv
import voluptuous as vol
import aiohttp
import time

from . import WundasmartDataUpdateCoordinator
from .pywundasmart import send_command
from .const import *

_LOGGER = logging.getLogger(__name__)

SUPPORTED_FEATURES = WaterHeaterEntityFeature.ON_OFF | WaterHeaterEntityFeature.OPERATION_MODE

OPERATION_AUTO = "auto"
OPERATION_BOOST_30 = "boost_30"
OPERATION_BOOST_60 = "boost_60"
OPERATION_BOOST_90 = "boost_90"
OPERATION_BOOST_120 = "boost_120"
OPERATION_OFF_30 = "off_30"
OPERATION_OFF_60 = "off_60"
OPERATION_OFF_90 = "off_90"
OPERATION_OFF_120 = "off_120"

HW_BOOST_OPERATIONS = {
    OPERATION_BOOST_30,
    OPERATION_BOOST_60,
    OPERATION_BOOST_90,
    OPERATION_BOOST_120
}

HW_OFF_OPERATIONS = {
    OPERATION_OFF_30,
    OPERATION_OFF_60,
    OPERATION_OFF_90,
    OPERATION_OFF_120
}

# Used when setting operation mode.
# We can't simply turn the hot water on or off without also specifying a duration.
OPERATION_MODE_ALIASES = {
    STATE_ON: OPERATION_BOOST_120,
    STATE_OFF: OPERATION_OFF_120
}


def _split_operation(key):
    """Return (operation prefix, duration in seconds)"""
    if "_" in key:
        key, duration = key.split("_", 1)
        if duration.isdigit():
            return key, int(duration) * 60
    return key, 0


async def async_setup_entry(
    hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback
) -> None:
    """Set up Wundasmart climate."""
    wunda_ip: str = entry.data[CONF_HOST]
    wunda_user: str = entry.data[CONF_USERNAME]
    wunda_pass: str = entry.data[CONF_PASSWORD]
    coordinator: WundasmartDataUpdateCoordinator = hass.data[DOMAIN][entry.entry_id]

    connect_timeout = entry.options.get(CONF_CONNECT_TIMEOUT, DEFAULT_CONNECT_TIMEOUT)
    read_timeout = entry.options.get(CONF_READ_TIMEOUT, DEFAULT_READ_TIMEOUT)
    timeout = aiohttp.ClientTimeout(sock_connect=connect_timeout, sock_read=read_timeout)

    async_add_entities(
        Device(
            wunda_ip,
            wunda_user,
            wunda_pass,
            wunda_id,
            device,
            coordinator,
            timeout
        )
        for wunda_id, device in coordinator.data.items() if device.get("device_type") == "wunda" and "device_name" in device
    )

    platform = entity_platform.current_platform.get()
    assert platform

    platform.async_register_entity_service(
        "hw_boost",
        {
            vol.Required("duration"): cv.positive_time_period
        },
        "async_set_boost",
    )

    platform.async_register_entity_service(
        "hw_off",
        {
            vol.Required("duration"): cv.positive_time_period
        },
        "async_set_off",
    )


class Device(CoordinatorEntity[WundasmartDataUpdateCoordinator], WaterHeaterEntity):
    """Representation of an Wundasmart water heater."""

    _attr_operation_list = [
        STATE_ON,
        STATE_OFF,
        OPERATION_AUTO
    ] + list(sorted(HW_BOOST_OPERATIONS | HW_OFF_OPERATIONS, key=_split_operation))

    _attr_supported_features = WaterHeaterEntityFeature.OPERATION_MODE | WaterHeaterEntityFeature.ON_OFF
    _attr_temperature_unit = UnitOfTemperature.CELSIUS
    _attr_translation_key = DOMAIN

    def __init__(
        self,
        wunda_ip: str,
        wunda_user: str,
        wunda_pass: str,
        wunda_id: str,
        device: dict[str, Any],
        coordinator: WundasmartDataUpdateCoordinator,
        timeout: aiohttp.ClientTimeout
    ) -> None:
        """Initialize the Wundasmart water_heater."""
        super().__init__(coordinator)
        self._wunda_ip = wunda_ip
        self._wunda_user = wunda_user
        self._wunda_pass = wunda_pass
        self._wunda_id = wunda_id
        self._attr_name = device["device_name"]
        self._attr_unique_id = device["id"]
        self._attr_type = device["device_type"]
        self._attr_device_info = coordinator.device_info
        self._timeout = timeout
        self._last_operation_mode = None
        self._last_operation_mode_timeout = 0

        # Update with initial state
        self.__update_state()

    def __update_state(self):
        device = self.coordinator.data.get(self._wunda_id)
        if device is not None and "state" in device and device.get("device_type") == "wunda":
            self._attr_current_operation = self.__infer_operation_mode(device["state"])

    def __infer_operation_mode(self, state):
        """Return the operation mode from the current device state."""
        try:
            # hw_mode_state is 1 if the hot water is on, 0 otherwise.
            hw_on = bool(int(state.get("hw_mode_state", 0)))
        except (ValueError, TypeError):
            _LOGGER.warning(f"Unexpected hw_mode_state '{state['hw_mode_state']}' for {self._attr_name}")
            hw_on = False

        try:
            # hw_boost_state is non-zero when a manual override/boost is active
            hw_override = bool(int(state.get("hw_boost_state", 0)))
        except (ValueError, TypeError):
            _LOGGER.warning(f"Unexpected hw_boost_state '{state['hw_boost_state']}' for {self._attr_name}")
            hw_override = False

        # If an override's been set, get operation mode based on the time left
        if hw_override:
            if hw_on and self._last_operation_mode in HW_BOOST_OPERATIONS:
                minutes_left = (self._last_operation_mode_timeout - time.time()) // 60
                if minutes_left > 90:
                    return OPERATION_BOOST_120
                elif minutes_left > 60:
                    return OPERATION_BOOST_90
                elif minutes_left > 30:
                    return OPERATION_BOOST_60
                elif minutes_left > 0:
                    return OPERATION_BOOST_30

            elif not hw_on and self._last_operation_mode in HW_OFF_OPERATIONS:
                minutes_left = (self._last_operation_mode_timeout - time.time()) // 60
                if minutes_left > 90:
                    return OPERATION_OFF_120
                elif minutes_left > 60:
                    return OPERATION_OFF_90
                elif minutes_left > 30:
                    return OPERATION_OFF_60
                elif minutes_left > 0:
                    return OPERATION_OFF_30

        # Otherwise just return the actual state as on or off
        return STATE_ON if hw_on else STATE_OFF

    @callback
    def _handle_coordinator_update(self) -> None:
        """Handle updated data from the coordinator."""
        self.__update_state()
        super()._handle_coordinator_update()

    async def async_added_to_hass(self) -> None:
        """When entity is added to hass."""
        await super().async_added_to_hass()
        self._handle_coordinator_update()

    async def async_set_operation_mode(self, operation_mode: str) -> None:
        duration = 0
        operation_mode = OPERATION_MODE_ALIASES.get(operation_mode, operation_mode)
        if operation_mode:
            if operation_mode in HW_OFF_OPERATIONS:
                _, duration = _split_operation(operation_mode)
                async with self.coordinator.get_session() as session:
                    await send_command(
                        session,
                        self._wunda_ip,
                        self._wunda_user,
                        self._wunda_pass,
                        timeout=self._timeout,
                        params={
                            "cmd": 3,
                            "hw_off_time": duration
                        })
            elif operation_mode in HW_BOOST_OPERATIONS:
                _, duration = _split_operation(operation_mode)
                async with self.coordinator.get_session() as session:
                    await send_command(
                        session,
                        self._wunda_ip,
                        self._wunda_user,
                        self._wunda_pass,
                        timeout=self._timeout,
                        params={
                            "cmd": 3,
                            "hw_boost_time": duration
                        })
            elif operation_mode == OPERATION_AUTO:
                async with self.coordinator.get_session() as session:
                    await send_command(
                        session,
                        self._wunda_ip,
                        self._wunda_user,
                        self._wunda_pass,
                        timeout=self._timeout,
                        params={
                            "cmd": 3,
                            "hw_boost_time": 0
                        })
            else:
                raise NotImplementedError(f"Unsupported operation mode {operation_mode}")

        # Remember the last operation mode that was set to use when getting the current operation mode.
        self._last_operation_mode = operation_mode
        self._last_operation_mode_timeout = time.time() + duration

        # Fetch the updated state
        await self.coordinator.async_request_refresh()

    async def async_set_boost(self, duration: timedelta):
        seconds = int((duration.days * 24 * 3600) + math.ceil(duration.seconds))
        if seconds > 0:
            async with self.coordinator.get_session() as session:
                await send_command(
                    session,
                    self._wunda_ip,
                    self._wunda_user,
                    self._wunda_pass,
                    timeout=self._timeout,
                    params={
                        "cmd": 3,
                        "hw_boost_time": seconds
                    })

        # Fetch the updated state
        await self.coordinator.async_request_refresh()

    async def async_set_off(self, duration: timedelta):
        seconds = int((duration.days * 24 * 3600) + math.ceil(duration.seconds))
        if seconds > 0:
            async with self.coordinator.get_session() as session:
                await send_command(
                    session,
                    self._wunda_ip,
                    self._wunda_user,
                    self._wunda_pass,
                    timeout=self._timeout,
                    params={
                        "cmd": 3,
                        "hw_off_time": seconds
                    })

        # Fetch the updated state
        await self.coordinator.async_request_refresh()
