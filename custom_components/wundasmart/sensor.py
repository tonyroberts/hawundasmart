"""Support for WundaSmart sensors."""
from __future__ import annotations
from dataclasses import dataclass, asdict
from collections import defaultdict
from typing import Literal
import itertools

from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.helpers.icon import icon_for_battery_level, icon_for_signal_level
from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorEntityDescription,
    SensorStateClass,
)
from homeassistant.const import (
    PERCENTAGE,
    SIGNAL_STRENGTH_DECIBELS_MILLIWATT,
    UnitOfTemperature
)

from . import WundasmartDataUpdateCoordinator
from .pywundasmart import get_room_id_from_device, get_device_id_ranges
from .const import *


def _number_or_none(x):
    try:
        return float(x)
    except (TypeError, ValueError):
        return None


@dataclass
class WundaSensorDescription(SensorEntityDescription):
    available: bool | callable = True
    default: float | None = None
    device_type: Literal["ROOM"] | Literal["TRV"] | Literal["SENSOR"] | None = None
    value_fn: callable | None = None

SENSORS: list[WundaSensorDescription] = [
    WundaSensorDescription(
        key="t_lo",
        device_type="ROOM",
        name="Reduced Preset",
        icon="mdi:thermometer",
        available=lambda state: float(state.get("t_lo", 0)) > 0,
        default=0.0,
        native_unit_of_measurement=UnitOfTemperature.CELSIUS,
        device_class=SensorDeviceClass.TEMPERATURE,
        state_class=SensorStateClass.MEASUREMENT,
    ),
    WundaSensorDescription(
        key="t_norm",
        device_type="ROOM",
        name="Eco Preset",
        icon="mdi:thermometer",
        available=lambda state: float(state.get("t_norm", 0)) > 0,
        default=0.0,
        native_unit_of_measurement=UnitOfTemperature.CELSIUS,
        device_class=SensorDeviceClass.TEMPERATURE,
        state_class=SensorStateClass.MEASUREMENT,
    ),
    WundaSensorDescription(
        key="t_hi",
        device_type="ROOM",
        name="Comfort Preset",
        icon="mdi:thermometer",
        available=lambda state: float(state.get("t_hi", 0)) > 0,
        default=0.0,
        native_unit_of_measurement=UnitOfTemperature.CELSIUS,
        device_class=SensorDeviceClass.TEMPERATURE,
        state_class=SensorStateClass.MEASUREMENT,
    ),
    WundaSensorDescription(
        key="temp",
        device_type="SENSOR",
        name="Temperature",
        icon="mdi:thermometer",
        native_unit_of_measurement=UnitOfTemperature.CELSIUS,
        device_class=SensorDeviceClass.TEMPERATURE,
        state_class=SensorStateClass.MEASUREMENT,
    ),
    WundaSensorDescription(
        key="rh",
        device_type="SENSOR",
        name="Humidity",
        icon="mdi:water-percent",
        native_unit_of_measurement=PERCENTAGE,
        device_class=SensorDeviceClass.HUMIDITY,
        state_class=SensorStateClass.MEASUREMENT,
    ),
    WundaSensorDescription(
        key="temp_ext",
        device_type="SENSOR",
        name="External Probe Temperature",
        icon="mdi:thermometer",
        available=lambda state: bool(int(state.get("ext", 0))),
        default=0.0,
        native_unit_of_measurement=UnitOfTemperature.CELSIUS,
        device_class=SensorDeviceClass.TEMPERATURE,
        state_class=SensorStateClass.MEASUREMENT,
    ),
    WundaSensorDescription(
        key="bat",
        device_type="SENSOR",
        name="Battery Level",
        icon=lambda x: icon_for_battery_level(_number_or_none(x)),
        native_unit_of_measurement=PERCENTAGE,
        device_class=SensorDeviceClass.BATTERY,
        state_class=SensorStateClass.MEASUREMENT,
    ),
    WundaSensorDescription(
        key="sig",
        device_type="SENSOR",
        name="Signal Level",
        value_fn=lambda state: _signal_pct_to_dbm(state.get("sig", None)),
        icon=lambda x: icon_for_signal_level(_signal_dbm_to_pct(x)),
        native_unit_of_measurement=SIGNAL_STRENGTH_DECIBELS_MILLIWATT,
        device_class=SensorDeviceClass.SIGNAL_STRENGTH,
        state_class=SensorStateClass.MEASUREMENT,
    ),
    WundaSensorDescription(
        key="vtemp",
        device_type="TRV",
        name="Temperature",
        icon="mdi:thermometer",
        native_unit_of_measurement=UnitOfTemperature.CELSIUS,
        device_class=SensorDeviceClass.TEMPERATURE,
        state_class=SensorStateClass.MEASUREMENT,
    ),
    WundaSensorDescription(
        key="bat",
        device_type="TRV",
        name="Battery Level",
        icon=lambda x: icon_for_battery_level(_number_or_none(x)),
        native_unit_of_measurement=PERCENTAGE,
        device_class=SensorDeviceClass.BATTERY,
        state_class=SensorStateClass.MEASUREMENT,
    ),
    WundaSensorDescription(
        key="sig",
        device_type="TRV",
        name="Signal Level",
        icon=lambda x: icon_for_signal_level(_signal_dbm_to_pct(x)),
        value_fn=lambda state: _signal_pct_to_dbm(state.get("sig", None)),
        native_unit_of_measurement=SIGNAL_STRENGTH_DECIBELS_MILLIWATT,
        device_class=SensorDeviceClass.SIGNAL_STRENGTH,
        state_class=SensorStateClass.MEASUREMENT,
    ),
    WundaSensorDescription(
        key="vpos",
        device_type="TRV",
        name="Position",
        state_class=SensorStateClass.MEASUREMENT,
    ),
    WundaSensorDescription(
        key="vpos_min",
        device_type="TRV",
        name="Position Min",
        state_class=SensorStateClass.MEASUREMENT,
    ),
    WundaSensorDescription(
        key="vpos_range",
        device_type="TRV",
        name="Position Range",
        state_class=SensorStateClass.MEASUREMENT,
    ),
    WundaSensorDescription(
        key="downforce",
        device_type="TRV",
        name="Downforce",
        state_class=SensorStateClass.MEASUREMENT,
    ),
    WundaSensorDescription(
        key="trv_range",
        device_type="TRV",
        name="TRV Range",
        state_class=SensorStateClass.MEASUREMENT,
    )
]


def _device_get_room(coordinator: WundasmartDataUpdateCoordinator, device):
    device_type = device.get("device_type")
    if device_type == "ROOM":
        return device
    elif device_type == "SENSOR":
        return _sensor_get_room(coordinator, device)
    elif device_type == "TRV":
        return _trv_get_room(coordinator, device)
    return None


def _sensor_get_room(coordinator: WundasmartDataUpdateCoordinator, device):
    """Return a room device dict for sensor"""
    room_id = get_room_id_from_device(device)
    return coordinator.data.get(room_id)


def _trv_get_room(coordinator: WundasmartDataUpdateCoordinator, device):
    """Return a room device dict for trv"""
    room_id = get_room_id_from_device(device)
    if room_id is not None:
        return coordinator.data.get(room_id)


def _trv_get_sensor_name(room, trv, desc: WundaSensorDescription):
    """Return a human readable name for a TRV device"""
    device_id = int(trv["device_id"])
    hw_version = float(trv["hw_version"])
    id_ranges = get_device_id_ranges(hw_version)
    return room["name"] + f" TRV.{device_id - id_ranges.MIN_TRV_ID} {desc.name}"


def _signal_pct_to_dbm(pct):
    """Convert signal percent to dBm"""
    if pct is None or pct == "":
        return None

    # For RSSI signal is between -50dBm and -100dBm
    # 100% = dBm >= -50 dBm
    # 0% = dBm <= -100 dBm
    pct = max(min(float(pct), 100), 0)
    return (pct / 2) - 100


def _signal_dbm_to_pct(dbm):
    if dbm is None or dbm == "":
        return None

    dbm = max(min(float(dbm), -50), -100)
    return (dbm + 100) * 2


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up the sensors from config entries."""
    coordinator: WundasmartDataUpdateCoordinator = hass.data[DOMAIN][entry.entry_id]

    devices_by_type = defaultdict(lambda: [])
    for wunda_id, device in coordinator.data.items():
        device_type = device.get("device_type")
        if device_type is not None:
            room = _device_get_room(coordinator, device)
            if room is not None and room.get("name") is not None:
                devices_by_type[device_type].append((wunda_id, device, room))

    descriptions_by_type = defaultdict(lambda: [])
    for desc in SENSORS:
        descriptions_by_type[desc.device_type].append(desc)

    sensors = itertools.chain(
        (
            Sensor(wunda_id,
               room["name"] + " " + desc.name,
               coordinator,
               desc)
                for wunda_id, device, room in devices_by_type["ROOM"]
                for desc in descriptions_by_type["ROOM"]
        ),

        (
            Sensor(wunda_id,
               room["name"] + " " + desc.name,
               coordinator,
               desc)
                for wunda_id, device, room in devices_by_type["SENSOR"]
                for desc in descriptions_by_type["SENSOR"]
        ),

        (
            Sensor(wunda_id,
               _trv_get_sensor_name(room, device, desc),
               coordinator,
               desc)
                for wunda_id, device, room in devices_by_type["TRV"]
                for desc in descriptions_by_type["TRV"]
        )
    )

    async_add_entities(sensors, update_before_add=True)


class Sensor(CoordinatorEntity[WundasmartDataUpdateCoordinator], SensorEntity):
    """Sensor entity for WundaSmart sensor values."""

    _attr_translation_key = DOMAIN

    def __init__(
        self,
        wunda_id: str,
        name: str,
        coordinator: WundasmartDataUpdateCoordinator,
        description: WundaSensorDescription,
    ) -> None:
        """Initialize the sensor."""
        super().__init__(coordinator)
        self._wunda_id = wunda_id
        self._coordinator = coordinator
        self._attr_name = name

        if (device_sn := coordinator.device_sn) is not None:
            self._attr_unique_id = f"{device_sn}.{wunda_id}.{description.key}"
        self._attr_device_info = coordinator.device_info

        self.entity_description = self.__update_description_defaults(description)

        # Update with initial state
        self.__update_state()

    @property
    def available(self):
        return self.__is_available(self.entity_description)

    def __is_available(self, description: WundaSensorDescription):
        if callable(description.available):
            device = self.coordinator.data.get(self._wunda_id, {})
            state = device.get("state", {})
            return description.available(state)
        return description.available

    def __update_description_defaults(self, description: WundaSensorDescription):
        kwargs = asdict(description)
        available = self.__is_available(description)
        kwargs["entity_registry_enabled_default"] = available
        kwargs["entity_registry_visible_default"] = available
        return WundaSensorDescription(**kwargs)

    def __update_state(self):
        device = self.coordinator.data.get(self._wunda_id, {})
        state = device.get("state", {})

        if self.entity_description.value_fn is not None:
            value = self.entity_description.value_fn(state)
        else:
            value = state.get(self.entity_description.key)

        if value is None and self.entity_description.default is not None:
            value = self.entity_description.default

        self._attr_native_value = value

    @callback
    def _handle_coordinator_update(self) -> None:
        """Handle updated data from the coordinator."""
        self.__update_state()
        super()._handle_coordinator_update()

    @property
    def icon(self) -> str:
        if callable(self.entity_description.icon):
            return self.entity_description.icon(self.state)
        return self.entity_description.icon
