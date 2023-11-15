from pytest_homeassistant_custom_component.common import MockConfigEntry
from pytest_homeassistant_custom_component.common import load_fixture
from custom_components.wundasmart.const import DOMAIN
from custom_components.wundasmart.water_heater import STATE_AUTO_ON, STATE_AUTO_OFF, STATE_BOOST_ON
from unittest.mock import patch
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator
from homeassistant.core import HomeAssistant

import json


async def test_water_header(hass: HomeAssistant, config):
    entry = MockConfigEntry(domain=DOMAIN, data=config)
    entry.add_to_hass(hass)

    # Test setup of water heater entity fetches initial state
    data = json.loads(load_fixture("test_get_devices1.json"))
    with patch("custom_components.wundasmart.get_devices", return_value=data):
        await hass.config_entries.async_setup(entry.entry_id)
        await hass.async_block_till_done()

        state = hass.states.get("water_heater.smart_hubswitch")

        assert state
        assert state.state == STATE_AUTO_ON

    coordinator: DataUpdateCoordinator = hass.data[DOMAIN][entry.entry_id]
    assert coordinator

    data = json.loads(load_fixture("test_get_devices2.json"))
    with patch("custom_components.wundasmart.get_devices", return_value=data):
        await coordinator.async_refresh()
        await hass.async_block_till_done()

        state = hass.states.get("water_heater.smart_hubswitch")

        assert state
        assert state.state == STATE_BOOST_ON

    data = json.loads(load_fixture("test_get_devices3.json"))
    with patch("custom_components.wundasmart.get_devices", return_value=data):
        await coordinator.async_refresh()
        await hass.async_block_till_done()

        state = hass.states.get("water_heater.smart_hubswitch")

        assert state
        assert state.state == STATE_AUTO_OFF


async def test_water_header_boost(hass: HomeAssistant, config):
    entry = MockConfigEntry(domain=DOMAIN, data=config)
    entry.add_to_hass(hass)

    # Test setup of water heater entity fetches initial state
    data = json.loads(load_fixture("test_get_devices1.json"))
    with patch("custom_components.wundasmart.get_devices", return_value=data), \
            patch("custom_components.wundasmart.water_heater.send_command", return_value=None) as mock:
        await hass.config_entries.async_setup(entry.entry_id)
        await hass.async_block_till_done()

        state = hass.states.get("water_heater.smart_hubswitch")
        assert state

        await hass.services.async_call("wundasmart", "hw_boost", {
            "entity_id": "water_heater.smart_hubswitch",
            "duration": "00:10:00"
        })
        await hass.async_block_till_done()

        # Check send_command was called correctly
        assert mock.call_count == 1
        assert mock.call_args.kwargs["params"]["cmd"] == 3
        assert mock.call_args.kwargs["params"]["hw_boost_time"] == 600
