"""Support for WundaSmart climate."""
from __future__ import annotations

import math
import logging
from typing import Any

from homeassistant.components.climate import (
    ClimateEntity,
    ClimateEntityFeature,
    HVACAction,
    HVACMode,
    PRESET_ECO,
    PRESET_COMFORT
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
from aiohttp import ClientSession

from . import WundasmartDataUpdateCoordinator
from .pywundasmart import send_command
from .const import DOMAIN, MIN_ROOM_ID, MIN_TRV_ID, MAX_TRV_ID

_LOGGER = logging.getLogger(__name__)

SUPPORTED_HVAC_MODES = [
    HVACMode.OFF,
    HVACMode.AUTO,
    HVACMode.HEAT,
]

PRESET_REDUCED = "reduced"

SUPPORTED_PRESET_MODES = [
    PRESET_REDUCED,
    PRESET_ECO,
    PRESET_COMFORT
]

PRESET_MODE_STATE_KEYS = {
    PRESET_REDUCED: "t_lo",
    PRESET_ECO: "t_norm",
    PRESET_COMFORT: "t_hi"
}

PARALLEL_UPDATES = 1


async def async_setup_entry(
    hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback
) -> None:
    """Set up Wundasmart climate."""
    wunda_ip: str = entry.data[CONF_HOST]
    wunda_user: str = entry.data[CONF_USERNAME]
    wunda_pass: str = entry.data[CONF_PASSWORD]
    coordinator: WundasmartDataUpdateCoordinator = hass.data[DOMAIN][entry.entry_id]
    session = aiohttp_client.async_get_clientsession(hass)
    rooms = (
        (wunda_id, device) for wunda_id, device
        in coordinator.data.items()
        if device.get("device_type") == "ROOM" and "name" in device
    )
    async_add_entities((Device(
            session,
            wunda_ip,
            wunda_user,
            wunda_pass,
            wunda_id,
            device,
            coordinator,
        )
        for wunda_id, device in rooms))


class Device(CoordinatorEntity[WundasmartDataUpdateCoordinator], ClimateEntity):
    """Representation of an Wundasmart climate."""

    _attr_hvac_modes = SUPPORTED_HVAC_MODES
    _attr_temperature_unit = TEMP_CELSIUS
    _attr_preset_modes = SUPPORTED_PRESET_MODES
    _attr_translation_key = DOMAIN

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
        """Initialize the Wundasmart climate."""
        super().__init__(coordinator)
        self._session = session
        self._wunda_ip = wunda_ip
        self._wunda_user = wunda_user
        self._wunda_pass = wunda_pass
        self._wunda_id = wunda_id
        self._attr_name = device["name"].replace("%20", " ")
        self._attr_unique_id = device["id"]
        self._attr_type = device["device_type"]
        self._attr_device_info = coordinator.device_info
        self._attr_supported_features = (
            ClimateEntityFeature.TARGET_TEMPERATURE | ClimateEntityFeature.PRESET_MODE
        )
        self._attr_current_temperature = None
        self._attr_target_temperature = None
        self._attr_current_humidity = None
        self._attr_hvac_mode = HVACMode.AUTO
        self._attr_preset_mode = None

        # Update with initial state
        self.__update_state()

    @property
    def __room(self):
        return self.coordinator.data.get(self._wunda_id, {})

    @property
    def __state(self):
        return self.__room.get("state", {})

    @property
    def __sensor_state(self):
        return self.__room.get("sensor_state", {})

    @property
    def __trvs(self):
        for trv in (self.coordinator.data.get(x, {}) for x in range(MIN_TRV_ID, MAX_TRV_ID+1)):
            room_id = trv.get("state", {}).get("room_id", None)
            if room_id is not None \
            and (isinstance(room_id, int) or (isinstance(room_id, str) and room_id.isdigit())) \
            and (int(room_id) + MIN_ROOM_ID) == self._wunda_id:
                yield trv

    def __set_current_temperature(self):
        """Set the current temperature from the coordinator data."""
        sensor_state = self.__sensor_state
        if sensor_state.get("temp") is not None:
            # If we've got a room thermostat then use the temperature from that
            try:
                self._attr_current_temperature = float(sensor_state["temp"])
            except (ValueError, TypeError):
                _LOGGER.warning(f"Unexpected temperature value '{sensor_state['temp']}' for {self._attr_name}")
            return

        # Otherwise look for TRVs in this room and use the avergage temperature from those
        trv_temps = []
        for trv in self.__trvs:
            try:
                trv_temp = float(trv.get("state", {}).get("vtemp", 0))
                if trv_temp:
                    trv_temps.append(trv_temp)
            except (ValueError, TypeError):
                pass

        if trv_temps:
            avg_temp = sum(trv_temps) / len(trv_temps)
            self._attr_current_temperature = avg_temp

    def __set_current_humidity(self):
        """Set the current humidity from the coordinator data."""
        sensor_state = self.__sensor_state
        if sensor_state.get("rh") is not None:
            try:
                self._attr_current_humidity = float(sensor_state["rh"])
            except (ValueError, TypeError):
                _LOGGER.warning(f"Unexpected humidity value '{sensor_state['rh']}' for {self._attr_name}")

    def __set_target_temperature(self):
        """Set the set temperature from the coordinator data."""
        state = self.__state
        if state.get("temp") is not None:
            try:
                self._attr_target_temperature = float(state["temp"])
            except (ValueError, TypeError):
                _LOGGER.warning(f"Unexpected set temp value '{state['temp']}' for {self._attr_name}")

    def __set_preset_mode(self):
        state = self.__state
        try:
            set_temp = float(state.get("temp", 0.0))
        except (ValueError, TypeError):
            _LOGGER.warning(f"Unexpected set temp value '{state['temp']}' for {self._attr_name}")
            return

        for preset_mode, state_key in PRESET_MODE_STATE_KEYS.items():
            if state.get(state_key) is not None:
                try:
                    t_preset = float(self.__state[state_key])
                    if t_preset == set_temp:
                        self._attr_preset_mode = preset_mode
                        break
                except (ValueError, TypeError):
                    _LOGGER.warning(f"Unexpected {state_key} value '{state[state_key]}' for {self._attr_name}")
        else:
            self._attr_preset_mode = None

    def __set_hvac_state(self):
        """Set the hvac action and hvac mode from the coordinator data."""
        state = self.__state
        if state.get("temp_pre") is not None:
            try:
                # tp appears to be the following flags:
                # - 00000001 (0x01) indicates a manual override is set until the next manual override
                # - 00000100 (0x04) indicates the set point temperature has been set to 'off'
                # - 00010000 (0x10) indicates a manual override has been set
                # - 00100000 (0x20) indicates heating demand
                # - 10000000 (0x80) indicates the adaptive start mode is active
                flags = int(state["temp_pre"])
                self._attr_hvac_mode = (
                    HVACMode.OFF if flags & (0x10 | 0x4) == (0x10 | 0x4)  # manually set to off
                    else HVACMode.HEAT if (flags & (0x10 | 0x80)) == 0x10  # manually set to heat
                    else HVACMode.AUTO
                )
                self._attr_hvac_action = (
                    HVACAction.PREHEATING if ((flags & (0x80 | 0x20)) == (0x80 | 0x20))
                    else HVACAction.HEATING if flags & 0x20 
                    else HVACAction.OFF if flags & 0x4
                    else HVACAction.IDLE
                )
            except (ValueError, TypeError):
                _LOGGER.warning(f"Unexpected 'temp_pre' value '{state['temp_pre']}' for {self._attr_name}")

    def __update_state(self):
        self.__set_current_temperature()
        self.__set_current_humidity()
        self.__set_target_temperature()
        self.__set_preset_mode()
        self.__set_hvac_state()

    @callback
    def _handle_coordinator_update(self) -> None:
        """Handle updated data from the coordinator."""
        self.__update_state()
        super()._handle_coordinator_update()

    async def async_added_to_hass(self) -> None:
        """When entity is added to hass."""
        await super().async_added_to_hass()
        self._handle_coordinator_update()

    async def async_set_temperature(self, temperature, **kwargs):
        # Set the new target temperature
        await send_command(self._session, self._wunda_ip, self._wunda_user, self._wunda_pass, params={
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
            await send_command(self._session, self._wunda_ip, self._wunda_user, self._wunda_pass, params={
                "cmd": 1,
                "roomid": self._wunda_id,
                "prog": None,
                "locktt": 0,
                "time": 0
            })
        elif hvac_mode == HVACMode.HEAT:
            # Set the target temperature to the current temperature + 1 degree, rounded up
            await send_command(self._session, self._wunda_ip, self._wunda_user, self._wunda_pass, params={
                "cmd": 1,
                "roomid": self._wunda_id,
                "temp": math.ceil(self._attr_current_temperature) + 1,
                "locktt": 0,
                "time": 0
            })
        elif hvac_mode == HVACMode.OFF:
            # Set the target temperature to zero
            await send_command(self._session, self._wunda_ip, self._wunda_user, self._wunda_pass, params={
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

    async def async_set_preset_mode(self, preset_mode) -> None:
        state_key = PRESET_MODE_STATE_KEYS.get(preset_mode)
        if state_key is None:
            raise NotImplementedError(f"Unsupported Preset mode {preset_mode}")
        
        t_preset = float(self.__state[state_key])

        await send_command(
            self._session,
            self._wunda_ip,
            self._wunda_user,
            self._wunda_pass,
            params={
                "cmd": 1,
                "roomid": self._wunda_id,
                "temp": t_preset,
                "locktt": 0,
                "time": 0,
            },
        )

        # Fetch the updated state
        await self.coordinator.async_request_refresh()
