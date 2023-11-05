"""Support for WundaSmart sensors."""
from __future__ import annotations
import itertools

from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity
from homeassistant.config_entries import ConfigEntry
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
from .const import *


ROOM_SENSORS: list[SensorEntityDescription] = [
    SensorEntityDescription(
        key="temp",
        name="Temperature",
        icon="mdi:thermometer",
        native_unit_of_measurement=UnitOfTemperature.CELSIUS,
        device_class=SensorDeviceClass.TEMPERATURE,
        state_class=SensorStateClass.MEASUREMENT,
    ),
    SensorEntityDescription(
        key="rh",
        name="Humidity",
        icon="mdi:water-percent",
        native_unit_of_measurement=PERCENTAGE,
        device_class=SensorDeviceClass.HUMIDITY,
        state_class=SensorStateClass.MEASUREMENT,
    ),
    SensorEntityDescription(
        key="bat",
        name="Battery Level",
        icon="mdi:battery",
        native_unit_of_measurement=PERCENTAGE,
        device_class=SensorDeviceClass.HUMIDITY,
        state_class=SensorStateClass.MEASUREMENT,
    )
]

TRV_SENSORS: list[SensorEntityDescription] = [
    SensorEntityDescription(
        key="vtemp",
        name="Temperature",
        icon="mdi:thermometer",
        native_unit_of_measurement=UnitOfTemperature.CELSIUS,
        device_class=SensorDeviceClass.TEMPERATURE,
        state_class=SensorStateClass.MEASUREMENT,
    ),
    SensorEntityDescription(
        key="bat",
        name="Battery Level",
        icon="mdi:battery",
        native_unit_of_measurement=PERCENTAGE,
        device_class=SensorDeviceClass.HUMIDITY,
        state_class=SensorStateClass.MEASUREMENT,
    )
]

def _sensor_get_room(coordinator: WundasmartDataUpdateCoordinator, sensor_id):
    """Return a room device dict for sensor"""
    room_id = int(sensor_id) - MIN_SENSOR_ID + MIN_ROOM_ID
    return coordinator.data.get(str(room_id) if isinstance(sensor_id, str) else room_id)


def _trv_get_room(coordinator: WundasmartDataUpdateCoordinator, trv_id):
    """Return a room device dict for trv"""
    trv = coordinator.data.get(trv_id, {})
    room_idx = trv.get("state", {}).get("room_id")
    if room_idx is not None:
        room_id = int(room_idx) + MIN_ROOM_ID
        return coordinator.data.get(str(room_id) if isinstance(trv_id, str) else room_id)


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
        and (room := _sensor_get_room(coordinator, wunda_id)) is not None
        and room.get("name") is not None
    )

    room_sensors = itertools.chain(
        Sensor(wunda_id,
               room["name"].replace("%20", " ") + " " + desc.name,
               coordinator,
               desc) for wunda_id, device, room in rooms
        for desc in ROOM_SENSORS
    )

    trvs = (
        (wunda_id, device, room) for wunda_id, device
        in coordinator.data.items()
        if device.get("device_type") == "TRV"
        and (room := _trv_get_room(coordinator, wunda_id)) is not None
        and room.get("name") is not None
    )

    trv_sensors = itertools.chain(
        Sensor(wunda_id,
               room["name"].replace("%20", " ") + f" TRV.{int(wunda_id)-MIN_TRV_ID} {desc.name}",
               coordinator,
               desc) for wunda_id, device, room in trvs
        for desc in TRV_SENSORS
    )

    async_add_entities(itertools.chain(room_sensors, trv_sensors), update_before_add=True)


class Sensor(CoordinatorEntity[WundasmartDataUpdateCoordinator], SensorEntity):
    """Sensor entity for WundaSmart sensor values."""

    def __init__(
        self,
        wunda_id: str,
        name: str,
        coordinator: WundasmartDataUpdateCoordinator,
        description: SensorEntityDescription,
    ) -> None:
        """Initialize the sensor."""
        super().__init__(coordinator)
        self._wunda_id = wunda_id
        self._attr_name = name

        if (device_sn := coordinator.device_sn) is not None:
            self._attr_unique_id = f"{device_sn}.{wunda_id}.{description.key}"
        self._attr_device_info = coordinator.device_info

        self.entity_description = description
        self._coordinator = coordinator

        # Update with initial state
        self.__update_state()

    def __update_state(self):
        device = self.coordinator.data.get(self._wunda_id, {})
        state = device.get("state", {})
        self._attr_available = True
        self._attr_native_value = state.get(self.entity_description.key)

    @callback
    def _handle_coordinator_update(self) -> None:
        """Handle updated data from the coordinator."""
        self.__update_state()
        super()._handle_coordinator_update()
