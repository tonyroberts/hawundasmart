from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.components.binary_sensor import BinarySensorEntity, BinarySensorDeviceClass
from homeassistant.config_entries import ConfigEntry
from homeassistant.helpers.event import async_track_time_interval
from homeassistant.const import CONF_HOST
from datetime import timedelta, datetime
from . import WundasmartDataUpdateCoordinator
from .const import DOMAIN, CONF_PING_INTERVAL, DEFAULT_PING_INTERVAL
from icmplib import async_ping, NameLookupError
import logging

_LOGGER = logging.getLogger(__name__)

ICMP_TIMEOUT = 1


async def async_setup_entry(
    hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback
) -> None:
    coordinator: WundasmartDataUpdateCoordinator = hass.data[DOMAIN][entry.entry_id]
    wunda_ip: str = entry.data[CONF_HOST]
    ping_interval = entry.options.get(CONF_PING_INTERVAL, DEFAULT_PING_INTERVAL)
    async_add_entities([WundaHeartbeatSensor(coordinator, wunda_ip, ping_interval)])


class WundaHeartbeatSensor(BinarySensorEntity):
    """Heartbeat sensor that pings the Wunda hub periodically."""

    def __init__(self, coordinator, wunda_ip, poll_interval):
        super().__init__()
        self._attr_device_class = BinarySensorDeviceClass.CONNECTIVITY
        self._attr_should_poll = False
        self._attr_device_info = coordinator.device_info
        self._attr_name = (coordinator.device_info or {}).get("name", "Smart HubSwitch")  + " Heartbeat"
        if coordinator.device_sn:
            self._attr_unique_id = f"wunda.{coordinator.device_sn}.heartbeat"
        self._wunda_ip = wunda_ip
        self._poll_interval = timedelta(seconds=poll_interval)
        self._unsub_timer = None
        self._state = False
        self._attributes = {}

    @property
    def is_on(self):
        return self._state

    @property
    def extra_state_attributes(self):
        return self._attributes

    async def async_added_to_hass(self):
        await super().async_added_to_hass()

        # Schedule periodic updates
        self._unsub_timer = async_track_time_interval(
            self.hass, self._async_poll, self._poll_interval
        )

        # Do first poll immediately
        await self._async_poll(None)

    async def async_will_remove_from_hass(self):
        await super().async_will_remove_from_hass()
        if self._unsub_timer:
            self._unsub_timer()
            self._unsub_timer = None

    async def _async_poll(self, now):
        await self.async_update_ha_state(force_refresh=True)

    async def async_update(self):
        try:
            data = await async_ping(
                self._wunda_ip,
                count=1,
                timeout=ICMP_TIMEOUT,
                privileged=False
            )
        except NameLookupError:
            _LOGGER.debug("Error resolving host: %s", self._wunda_ip)
            self._state = False
            self._attributes = {}
            return
        except Exception as err:
            _LOGGER.debug("Ping failed for %s: %s", self._wunda_ip, err)
            self._state = False
            self._attributes = {}
            return

        _LOGGER.debug(
            "async_ping %s: reachable=%s sent=%i received=%s",
            self._attr_name,
            data.is_alive,
            data.packets_sent,
            data.packets_received,
        )

        self._state = data.is_alive
        if not self._state:
            self._attributes = {}
            return

        self._attributes = {
            "lastseen": datetime.now().isoformat(),
            "min": data.min_rtt,
            "max": data.max_rtt,
            "avg": data.avg_rtt,
            "jitter": data.jitter,
        }
