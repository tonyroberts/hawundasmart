from pytest_homeassistant_custom_component.common import MockConfigEntry
from pytest_homeassistant_custom_component.common import load_fixture
from custom_components.wundasmart.const import DOMAIN
from custom_components.wundasmart.water_heater import STATE_AUTO_ON, STATE_AUTO_OFF, STATE_BOOST_ON
from unittest.mock import patch
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator
from homeassistant.core import HomeAssistant

import json


async def test_sensors(hass: HomeAssistant, config):
    entry = MockConfigEntry(domain=DOMAIN, data=config)
    entry.add_to_hass(hass)

    # Test setup of sensor entities fetches initial state
    data = json.loads(load_fixture("test_get_devices1.json"))
    with patch("custom_components.wundasmart.get_devices", return_value=data):
        await hass.config_entries.async_setup(entry.entry_id)
        await hass.async_block_till_done()

        temp_state = hass.states.get("sensor.test_room_temperature")
        assert temp_state
        assert temp_state.state == "17.8"

        rh_state = hass.states.get("sensor.test_room_humidity")        
        assert rh_state
        assert rh_state.state == "66.57"


    coordinator: DataUpdateCoordinator = hass.data[DOMAIN][entry.entry_id]
    assert coordinator

    data = json.loads(load_fixture("test_get_devices2.json"))
    with patch("custom_components.wundasmart.get_devices", return_value=data):
        await coordinator.async_refresh()
        await hass.async_block_till_done()

        temp_state = hass.states.get("sensor.test_room_temperature")
        assert temp_state
        assert temp_state.state == "16.0"

        rh_state = hass.states.get("sensor.test_room_humidity")        
        assert rh_state
        assert rh_state.state == "50.0"
