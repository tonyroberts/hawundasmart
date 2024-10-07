from pytest_homeassistant_custom_component.common import MockConfigEntry
from pytest_homeassistant_custom_component.common import load_fixture
from custom_components.wundasmart.const import DOMAIN
from unittest.mock import patch
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator
from homeassistant.core import HomeAssistant
from .utils import deserialize_get_devices_fixture

import json


async def test_sensors(hass: HomeAssistant, config):
    entry = MockConfigEntry(domain=DOMAIN, data=config)
    entry.add_to_hass(hass)

    # Test setup of sensor entities fetches initial state
    data = deserialize_get_devices_fixture(load_fixture("test_get_devices1.json"))
    with patch("custom_components.wundasmart.get_devices", return_value=data):
        await hass.config_entries.async_setup(entry.entry_id)
        await hass.async_block_till_done()

        temp_state = hass.states.get("sensor.test_room_temperature")
        assert temp_state
        assert temp_state.state == "17.8"

        rh_state = hass.states.get("sensor.test_room_humidity")
        assert rh_state
        assert rh_state.state == "66.57"

        trv_battery_state = hass.states.get("sensor.test_room_trv_0_battery_level")
        assert trv_battery_state
        assert trv_battery_state.state == "100"
        assert trv_battery_state.attributes["icon"] == "mdi:battery"

        trv_signal_state = hass.states.get("sensor.test_room_trv_0_signal_level")
        assert trv_signal_state
        assert trv_signal_state.state == "-50.0"
        assert trv_signal_state.attributes["icon"] == "mdi:signal-cellular-3"

        ext_temp_state = hass.states.get("sensor.test_room_external_probe_temperature")
        assert ext_temp_state
        assert ext_temp_state.state == "18.0"

        t_lo_state = hass.states.get("sensor.test_room_reduced_preset")
        assert t_lo_state
        assert t_lo_state.state == "14.00"

        t_norm_state = hass.states.get("sensor.test_room_eco_preset")
        assert t_norm_state
        assert t_norm_state.state == "19.00"

        t_hi_state = hass.states.get("sensor.test_room_comfort_preset")
        assert t_hi_state
        assert t_hi_state.state == "21.00"

    coordinator: DataUpdateCoordinator = hass.data[DOMAIN][entry.entry_id]
    assert coordinator

    data = deserialize_get_devices_fixture(load_fixture("test_get_devices2.json"))
    with patch("custom_components.wundasmart.get_devices", return_value=data):
        await coordinator.async_refresh()
        await hass.async_block_till_done()

        temp_state = hass.states.get("sensor.test_room_temperature")
        assert temp_state
        assert temp_state.state == "16.0"

        rh_state = hass.states.get("sensor.test_room_humidity")
        assert rh_state
        assert rh_state.state == "50.0"

        sig_state = hass.states.get("sensor.test_room_signal_level")
        assert sig_state
        assert sig_state.state == "-95.0"
        assert sig_state.attributes["icon"] == "mdi:signal-cellular-1"

        trv_battery_state = hass.states.get("sensor.test_room_trv_0_battery_level")
        assert trv_battery_state
        assert trv_battery_state.state == "50"
        assert trv_battery_state.attributes["icon"] == "mdi:battery-50"

        trv_signal_state = hass.states.get("sensor.test_room_trv_0_signal_level")
        assert trv_signal_state
        assert trv_signal_state.state == "-75.0"
        assert trv_signal_state.attributes["icon"] == "mdi:signal-cellular-2"