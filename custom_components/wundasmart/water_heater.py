"""Support for WundaSmart water heater."""
from __future__ import annotations

import logging
from typing import Any

from aiohttp.client import ClientSession

from homeassistant.components.water_heater import (
    WaterHeaterEntity,
    WaterHeaterEntityFeature,
    STATE_GAS
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import (
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

SUPPORTED_FEATURES = WaterHeaterEntityFeature.ON_OFF | WaterHeaterEntityFeature.OPERATION_MODE

STATE_AUTO_ON = "On (Auto)"
STATE_AUTO_OFF = "Off (Auto)"
STATE_BOOST_ON = "On (Boost)"
STATE_BOOST_OFF = "Off (Manual)"
STATE_AUTO = "Auto"

HW_BOOST_TIME = 60 * 30  # boost for 30 minutes
HW_OFF_TIME = 60 * 60  # switch off for 1 hour

OPERATION_SET_AUTO = "Auto"
OPERATION_BOOST_ON = "Boost (30 mins)"
OPERATION_BOOST_OFF = "Off (1 hour)"


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
            aiohttp_client.async_get_clientsession(hass),
            wunda_ip,
            wunda_user,
            wunda_pass,
            wunda_id,
            device,
            coordinator,
        )
        for wunda_id, device in coordinator.data.items() if device.get("device_type") == "wunda" and "device_name" in device
    )


class Device(CoordinatorEntity[WundasmartDataUpdateCoordinator], WaterHeaterEntity):
    """Representation of an Wundasmart water heater."""

    _attr_operation_list = [
        OPERATION_SET_AUTO,
        OPERATION_BOOST_ON,
        OPERATION_BOOST_OFF
    ]

    _attr_supported_features = WaterHeaterEntityFeature.OPERATION_MODE

    _attr_temperature_unit = TEMP_CELSIUS

    def __init__(
        self,
        session: ClientSession,
        wunda_ip: str,
        wunda_user: str,
        wunda_pass: str,
        wunda_id: str,
        device: dict[str, Any],
        coordinator: WundasmartDataUpdateCoordinator,
    ) -> None:
        """Initialize the Wundasmart water_heater."""
        super().__init__(coordinator)
        self._session = session
        self._wunda_ip = wunda_ip
        self._wunda_user = wunda_user
        self._wunda_pass = wunda_pass
        self._wunda_id = wunda_id
        self._attr_name = device["device_name"].replace("%20", " ")
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

    @callback
    def _handle_coordinator_update(self) -> None:
        """Handle updated data from the coordinator."""
        device = self.coordinator.data.get(self._wunda_id)
        if device is not None and "state" in device and device.get("device_type") == "wunda":
            state = device["state"]

            try:
                hw_mode_state = bool(int(state.get("hw_mode_state", 0)))
            except (ValueError, TypeError):
                _LOGGER.warning(f"Unexpected hw_mode_state '{state['hw_mode_state']}' for {self._attr_name}")
                hw_mode_state = False

            try:
                hw_boost_state = bool(int(state.get("hw_boost_state", 0)))
            except (ValueError, TypeError):
                _LOGGER.warning(f"Unexpected hw_boost_state '{state['hw_boost_state']}' for {self._attr_name}")
                hw_boost_state = False

            # - hw_mode_state is 1 if the hot water is on, 0 otherwise.
            # - hw_boost_state is non-zero when a manual override/boost is active
            #   1 => manually on, 2 => manually off
            if hw_mode_state:
                self._attr_current_operation = STATE_BOOST_ON if hw_boost_state else STATE_AUTO_ON
            else:
                self._attr_current_operation = STATE_BOOST_OFF if hw_boost_state else STATE_AUTO_OFF

        super()._handle_coordinator_update()

    async def async_added_to_hass(self) -> None:
        """When entity is added to hass."""
        await super().async_added_to_hass()
        self._handle_coordinator_update()

    async def async_set_operation_mode(self, operation_mode: str) -> None:
        if operation_mode == OPERATION_BOOST_OFF:
            await send_command(self._session, self._wunda_ip, self._wunda_user, self._wunda_pass, params={
                "cmd": 3,
                "hw_off_time": HW_OFF_TIME
            })
        elif operation_mode == OPERATION_BOOST_ON:
            await send_command(self._session, self._wunda_ip, self._wunda_user, self._wunda_pass, params={
                "cmd": 3,
                "hw_boost_time": HW_BOOST_TIME
            })
        elif operation_mode == OPERATION_SET_AUTO:
            await send_command(self._session, self._wunda_ip, self._wunda_user, self._wunda_pass, params={
                "cmd": 3,
                "hw_boost_time": 0
            })
        else:
            raise NotImplementedError(f"Unsupported operation mode {operation_mode}")

        # Fetch the updated state
        await self.coordinator.async_request_refresh()
