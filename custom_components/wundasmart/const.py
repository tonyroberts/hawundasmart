"""Constants for the wundasmart integration."""
from dataclasses import dataclass
from homeassistant.components.climate.const import (
    PRESET_ECO,
    PRESET_COMFORT
)

DOMAIN = "wundasmart"

CONF_CONNECT_TIMEOUT = "connect_timeout"
CONF_READ_TIMEOUT = "read_timeout"
CONF_PING_INTERVAL = "ping_interval"

DEFAULT_SCAN_INTERVAL = 300
DEFAULT_CONNECT_TIMEOUT = 5
DEFAULT_READ_TIMEOUT = 5
DEFAULT_PING_INTERVAL = 180

@dataclass
class DeviceIdRanges:
    MIN_SENSOR_ID: int
    MAX_SENSOR_ID: int
    MIN_TRV_ID: int
    MAX_TRV_ID: int
    MIN_UFH_ID: int
    MAX_UFH_ID: int
    MIN_ROOM_ID: int
    MAX_ROOM_ID: int


DEVICE_ID_RANGES = {
    # HW version
    2: DeviceIdRanges(
        MIN_SENSOR_ID=1,
        MAX_SENSOR_ID=30,
        MIN_TRV_ID=31, # TRV min/max is a guess, no data to confirm
        MAX_TRV_ID=79,
        MIN_UFH_ID=80,
        MAX_UFH_ID=84,
        MIN_ROOM_ID=100,
        MAX_ROOM_ID=119
    ),
    4: DeviceIdRanges(
        MIN_SENSOR_ID=1,
        MAX_SENSOR_ID=30,
        MIN_TRV_ID=31,
        MAX_TRV_ID=89,
        MIN_UFH_ID=90,
        MAX_UFH_ID=94,
        MIN_ROOM_ID=121,
        MAX_ROOM_ID=150
    )
}
