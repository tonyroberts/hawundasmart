"""Support for WundaSmart sensors."""
from __future__ import annotations
from dataclasses import dataclass, asdict
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


ROOM_SENSORS: list[WundaSensorDescription] = [
    WundaSensorDescription(
        key="temp",
        name="Temperature",
        icon="mdi:thermometer",
        native_unit_of_measurement=UnitOfTemperature.CELSIUS,
        device_class=SensorDeviceClass.TEMPERATURE,
        state_class=SensorStateClass.MEASUREMENT,
    ),
    WundaSensorDescription(
        key="rh",
        name="Humidity",
        icon="mdi:water-percent",
        native_unit_of_measurement=PERCENTAGE,
        device_class=SensorDeviceClass.HUMIDITY,
        state_class=SensorStateClass.MEASUREMENT,
    ),
    WundaSensorDescription(
        key="temp_ext",
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
        name="Battery Level",
        icon=lambda x: icon_for_battery_level(_number_or_none(x)),
        native_unit_of_measurement=PERCENTAGE,
        device_class=SensorDeviceClass.BATTERY,
        state_class=SensorStateClass.MEASUREMENT,
    ),
    WundaSensorDescription(
        key="sig",
        name="Signal Level",
        icon=lambda x: icon_for_signal_level(_number_or_none(x)),
        native_unit_of_measurement=PERCENTAGE,
        device_class=SensorDeviceClass.SIGNAL_STRENGTH,
        state_class=SensorStateClass.MEASUREMENT,
    )
]

TRV_SENSORS: list[WundaSensorDescription] = [
    WundaSensorDescription(
        key="vtemp",
        name="Temperature",
        icon="mdi:thermometer",
        native_unit_of_measurement=UnitOfTemperature.CELSIUS,
        device_class=SensorDeviceClass.TEMPERATURE,
        state_class=SensorStateClass.MEASUREMENT,
    ),
    WundaSensorDescription(
        key="bat",
        name="Battery Level",
        icon=lambda x: icon_for_battery_level(_number_or_none(x)),
        native_unit_of_measurement=PERCENTAGE,
        device_class=SensorDeviceClass.BATTERY,
        state_class=SensorStateClass.MEASUREMENT,
    ),
    WundaSensorDescription(
        key="sig",
        name="Signal Level",
        icon=lambda x: icon_for_signal_level(_number_or_none(x)),
        native_unit_of_measurement=PERCENTAGE,
        device_class=SensorDeviceClass.SIGNAL_STRENGTH,
        state_class=SensorStateClass.MEASUREMENT,
    ),
    WundaSensorDescription(
        key="vpos",
        name="Position",
        state_class=SensorStateClass.MEASUREMENT,
    ),
    WundaSensorDescription(
        key="vpos_min",
        name="Position Min",
        state_class=SensorStateClass.MEASUREMENT,
    ),
    WundaSensorDescription(
        key="vpos_range",
        name="Position Range",
        state_class=SensorStateClass.MEASUREMENT,
    ),
    WundaSensorDescription(
        key="downforce",
        name="Downforce",
        state_class=SensorStateClass.MEASUREMENT,
    ),
    WundaSensorDescription(
        key="trv_range",
        name="TRV Range",
        state_class=SensorStateClass.MEASUREMENT,
    )
]


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


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up the sensors from config entries."""
    coordinator: WundasmartDataUpdateCoordinator = hass.data[DOMAIN][entry.entry_id]

    rooms = (
        (wunda_id, device, room) for wunda_id, device
        in coordinator.data.items()
        if device.get("device_type") == "SENSOR"
        and (room := _sensor_get_room(coordinator, device)) is not None
        and room.get("name") is not None
    )

    room_sensors = itertools.chain(
        Sensor(wunda_id,
               room["name"] + " " + desc.name,
               coordinator,
               desc) for wunda_id, device, room in rooms
        for desc in ROOM_SENSORS
    )

    trvs = list((
        (wunda_id, device, room) for wunda_id, device
        in coordinator.data.items()
        if device.get("device_type") == "TRV"
        and (room := _trv_get_room(coordinator, device)) is not None
        and room.get("name") is not None
    ))

    trv_sensors = itertools.chain(
        Sensor(wunda_id,
               _trv_get_sensor_name(room, device, desc),
               coordinator,
               desc) for wunda_id, device, room in trvs
        for desc in TRV_SENSORS
    )

    async_add_entities(itertools.chain(room_sensors, trv_sensors), update_before_add=True)


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
        value = state.get(self.entity_description.key)
        if not value and self.entity_description.default is not None:
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
