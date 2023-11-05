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
from .const import DOMAIN


SENSORS: list[SensorEntityDescription] = [
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
    )
]


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up the sensors from config entries."""
    coordinator: WundasmartDataUpdateCoordinator = hass.data[DOMAIN][entry.entry_id]

    rooms = (
        (wunda_id, device) for wunda_id, device
        in coordinator.data.items()
        if device.get("device_type") == "ROOM" and "name" in device
    )

    sensors = itertools.chain(
        Sensor(wunda_id,
               device["name"].replace("%20", " ") + " " + desc.name,
               coordinator,
               desc) for wunda_id, device in rooms
        for desc in SENSORS
    )

    async_add_entities(sensors, update_before_add=True)


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
        sensor_state = device.get("sensor_state", {})
        self._attr_available = True
        self._attr_native_value = sensor_state.get(self.entity_description.key)

    @callback
    def _handle_coordinator_update(self) -> None:
        """Handle updated data from the coordinator."""
        self.__update_state()
        super()._handle_coordinator_update()
