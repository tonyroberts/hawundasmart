"""Support for WundaSmart climate."""
from __future__ import annotations

import logging
import aiohttp
from typing import Any
import voluptuous as vol

from homeassistant.components.climate import ClimateEntity
from homeassistant.components.climate.const import (
    ClimateEntityFeature,
    HVACAction,
    HVACMode,
    PRESET_ECO,
    PRESET_COMFORT,
    PRESET_NONE
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import (
    CONF_HOST,
    CONF_USERNAME,
    CONF_PASSWORD,
    UnitOfTemperature,
)
from homeassistant.core import HomeAssistant, ServiceCall, callback
from homeassistant.helpers.entity_platform import AddEntitiesCallback, async_get_current_platform
from homeassistant.helpers.update_coordinator import CoordinatorEntity
from homeassistant.helpers import config_validation as cv

from . import WundasmartDataUpdateCoordinator
from .pywundasmart import send_command, set_register, get_room_id_from_device
from .const import *

_LOGGER = logging.getLogger(__name__)

SERVICE_SET_PRESET_TEMPERATURE = "set_preset_temperature"

SUPPORTED_HVAC_MODES = [
    HVACMode.OFF,
    HVACMode.AUTO,
    HVACMode.HEAT,
]

PRESET_REDUCED = "reduced"

SUPPORTED_PRESET_MODES = [
    PRESET_NONE,
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

    connect_timeout = entry.options.get(CONF_CONNECT_TIMEOUT, DEFAULT_CONNECT_TIMEOUT)
    read_timeout = entry.options.get(CONF_READ_TIMEOUT, DEFAULT_READ_TIMEOUT)
    timeout = aiohttp.ClientTimeout(sock_connect=connect_timeout, sock_read=read_timeout)

    rooms = (
        (wunda_id, device) for wunda_id, device
        in coordinator.data.items()
        if device.get("device_type") == "ROOM" and "name" in device
    )
    async_add_entities((Device(
            wunda_ip,
            wunda_user,
            wunda_pass,
            wunda_id,
            device,
            coordinator,
            timeout
        )
        for wunda_id, device in rooms))

    platform = async_get_current_platform()

    platform.async_register_entity_service(
        SERVICE_SET_PRESET_TEMPERATURE,
        {
            vol.Required('preset'): vol.In(SUPPORTED_PRESET_MODES, msg="invalid preset"),
            vol.Required('temperature'): cv.Number
        },
        Device.async_set_preset_temperature,
    )


class Device(CoordinatorEntity[WundasmartDataUpdateCoordinator], ClimateEntity):
    """Representation of an Wundasmart climate."""

    _attr_hvac_modes = SUPPORTED_HVAC_MODES
    _attr_temperature_unit = UnitOfTemperature.CELSIUS
    _attr_preset_modes = SUPPORTED_PRESET_MODES
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
        """Initialize the Wundasmart climate."""
        super().__init__(coordinator)
        self._wunda_ip = wunda_ip
        self._wunda_user = wunda_user
        self._wunda_pass = wunda_pass
        self._wunda_id = wunda_id
        self._attr_name = device["name"]
        self._attr_unique_id = device["id"]
        self._attr_type = device["device_type"]
        self._attr_device_info = coordinator.device_info
        # This flag needs to be set until 2025.1 to prevent warnings about
        # implicitly supporting the turn_off/turn_on methods.
        # https://developers.home-assistant.io/blog/2024/01/24/climate-climateentityfeatures-expanded/
        self._enable_turn_on_off_backwards_compatibility = False
        self._attr_supported_features = (
            ClimateEntityFeature.TARGET_TEMPERATURE
            | ClimateEntityFeature.PRESET_MODE
            | ClimateEntityFeature.TURN_ON
            | ClimateEntityFeature.TURN_OFF
        )
        self._attr_current_temperature = None
        self._attr_target_temperature = None
        self._attr_current_humidity = None
        self._attr_hvac_mode = HVACMode.AUTO
        self._attr_preset_mode = PRESET_NONE
        self._timeout = timeout

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
        for device in self.coordinator.data.values():
            if device.get("device_type") == "TRV":
                room_id = get_room_id_from_device(device)
                if room_id is not None and int(room_id) == int(self._wunda_id):
                    yield device

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
            self._attr_preset_mode = PRESET_NONE

    def __set_hvac_state(self):
        """Set the hvac action and hvac mode from the coordinator data."""
        state = self.__state

        temp_pre = 0
        if state.get("temp_pre") is not None:
            try:
                # temp_pre appears to be the following flags:
                # - 0000 0001 (0x01) indicates a manual override is set until the next manual override
                # - 0000 0100 (0x04) indicates the set point temperature has been set to 'off'
                # - 0001 0000 (0x10) indicates a manual override has been set
                # - 0010 0000 (0x20) indicates heating demand
                # - 1000 0000 (0x80) indicates the adaptive start mode is active
                temp_pre = int(state["temp_pre"])
            except (ValueError, TypeError):
                _LOGGER.warning(f"Unexpected 'temp_pre' value '{state['temp_pre']}' for {self._attr_name}")

        heat = 0
        if state.get("heat") is not None:
            try:
                # heat appears to be the following flags:
                # - 0000 0001 (0x01) indicates heat is being delivered
                # - 0000 0010 (0x02) indicates heating demand
                # - 0000 0100 (0x04) not sure what this means, always seem to be set
                #
                # eg. when off, heat is 4
                #     demand but no heat delivered (pump delay?), heat is 6
                #     demand and providing heat, heat is 7
                #     no demand but heat still on (pump delay?), heat is 5
                heat = int(state["heat"])
            except (ValueError, TypeError):
                _LOGGER.warning(f"Unexpected 'heat' value '{state['heat']}' for {self._attr_name}")

        self._attr_hvac_mode = (
            HVACMode.OFF if temp_pre & (0x10 | 0x4) == (0x10 | 0x4)  # manually set to off
            else HVACMode.HEAT if (temp_pre & (0x10 | 0x80)) == 0x10  # manually set to heat
            else HVACMode.AUTO
        )

        adaptive_start = temp_pre & 0x80
        heating = heat & 0x1
        demand = heat & 0x2

        self._attr_hvac_action = (
            HVACAction.PREHEATING if adaptive_start and heating
            else HVACAction.HEATING if heating and demand
            else HVACAction.IDLE if heating or demand
            else HVACAction.OFF
        )

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
        async with self.coordinator.get_session() as session:
            await send_command(
                session,
                self._wunda_ip,
                self._wunda_user,
                self._wunda_pass,
                timeout=self._timeout,
                params={
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
            async with self.coordinator.get_session() as session:
                await send_command(
                    session,
                    self._wunda_ip,
                    self._wunda_user,
                    self._wunda_pass,
                    timeout=self._timeout,
                    params={
                        "cmd": 1,
                        "roomid": self._wunda_id,
                        "prog": None,
                        "locktt": 0,
                        "time": 0
                    })
        elif hvac_mode == HVACMode.HEAT:
            # Set the target temperature to the t_hi preset temp
            async with self.coordinator.get_session() as session:
                await send_command(
                    session,
                    self._wunda_ip,
                    self._wunda_user,
                    self._wunda_pass,
                    timeout=self._timeout,
                    params={
                        "cmd": 1,
                        "roomid": self._wunda_id,
                        "temp": float(self.__state["t_hi"]),
                        "locktt": 0,
                        "time": 0
                    })
        elif hvac_mode == HVACMode.OFF:
            # Set the target temperature to zero
            async with self.coordinator.get_session() as session:
                await send_command(
                    session,
                    self._wunda_ip,
                    self._wunda_user,
                    self._wunda_pass,
                    timeout=self._timeout,
                    params={
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
        if preset_mode and preset_mode != PRESET_NONE:
            state_key = PRESET_MODE_STATE_KEYS.get(preset_mode)
            if state_key is None:
                raise NotImplementedError(f"Unsupported Preset mode {preset_mode}")

            t_preset = float(self.__state[state_key])

            async with self.coordinator.get_session() as session:
                await send_command(
                    session,
                    self._wunda_ip,
                    self._wunda_user,
                    self._wunda_pass,
                    timeout=self._timeout,
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

    async def async_turn_on(self) -> None:
        """Turn the entity on."""
        await self.async_set_hvac_mode(HVACMode.HEAT)

    async def async_turn_off(self) -> None:
        """Turn the entity off."""
        await self.async_set_hvac_mode(HVACMode.OFF)

    async def async_set_preset_temperature(self, service_data: ServiceCall) -> None:
        """Change one of the preset temperatures."""
        preset = service_data.data["preset"]
        temperature = service_data.data["temperature"]

        async with self.coordinator.get_session() as session:
            await set_register(
                session,
                self._wunda_ip,
                self._wunda_user,
                self._wunda_pass,
                timeout=self._timeout,
                device_id=self._wunda_id,
                register_id=PRESET_MODE_STATE_KEYS[preset],
                value=temperature)

        # Fetch the updated state
        await self.coordinator.async_request_refresh()
