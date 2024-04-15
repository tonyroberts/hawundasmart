from pytest_homeassistant_custom_component.common import MockConfigEntry
from pytest_homeassistant_custom_component.common import load_fixture
from custom_components.wundasmart.const import DOMAIN
from custom_components.wundasmart.water_heater import STATE_ON, STATE_OFF
from unittest.mock import patch
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator
from homeassistant.core import HomeAssistant
from .utils import deserialize_get_devices_fixture

import json


async def test_water_header(hass: HomeAssistant, config):
    entry = MockConfigEntry(domain=DOMAIN, data=config)
    entry.add_to_hass(hass)

    # Test setup of water heater entity fetches initial state
    data = deserialize_get_devices_fixture(load_fixture("test_get_devices1.json"))
    with patch("custom_components.wundasmart.get_devices", return_value=data):
        await hass.config_entries.async_setup(entry.entry_id)
        await hass.async_block_till_done()

        state = hass.states.get("water_heater.smart_hubswitch")

        assert state
        assert state.state == STATE_ON

    coordinator: DataUpdateCoordinator = hass.data[DOMAIN][entry.entry_id]
    assert coordinator

    data = deserialize_get_devices_fixture(load_fixture("test_get_devices2.json"))
    with patch("custom_components.wundasmart.get_devices", return_value=data):
        await coordinator.async_refresh()
        await hass.async_block_till_done()

        state = hass.states.get("water_heater.smart_hubswitch")

        assert state
        assert state.state == STATE_ON

    data = deserialize_get_devices_fixture(load_fixture("test_get_devices3.json"))
    with patch("custom_components.wundasmart.get_devices", return_value=data):
        await coordinator.async_refresh()
        await hass.async_block_till_done()

        state = hass.states.get("water_heater.smart_hubswitch")

        assert state
        assert state.state == STATE_OFF


async def test_water_header_set_operation(hass: HomeAssistant, config):
    entry = MockConfigEntry(domain=DOMAIN, data=config)
    entry.add_to_hass(hass)

    data = deserialize_get_devices_fixture(load_fixture("test_get_devices1.json"))
    with patch("custom_components.wundasmart.get_devices", return_value=data), \
            patch("custom_components.wundasmart.water_heater.send_command", return_value=None) as mock:
        await hass.config_entries.async_setup(entry.entry_id)
        await hass.async_block_till_done()

        state = hass.states.get("water_heater.smart_hubswitch")
        assert state

        await hass.services.async_call("water_heater", "set_operation_mode", {
            "entity_id": "water_heater.smart_hubswitch",
            "operation_mode": "boost_30"
        })
        await hass.async_block_till_done()

        # Check send_command was called correctly
        assert mock.call_count == 1
        assert mock.call_args.kwargs["params"]["cmd"] == 3
        assert mock.call_args.kwargs["params"]["hw_boost_time"] == 1800

        await hass.services.async_call("water_heater", "set_operation_mode", {
            "entity_id": "water_heater.smart_hubswitch",
            "operation_mode": "off_60"
        })
        await hass.async_block_till_done()

        assert mock.call_count == 2
        assert mock.call_args.kwargs["params"]["cmd"] == 3
        assert mock.call_args.kwargs["params"]["hw_off_time"] == 3600


async def test_water_header_boost(hass: HomeAssistant, config):
    entry = MockConfigEntry(domain=DOMAIN, data=config)
    entry.add_to_hass(hass)

    # Test setup of water heater entity fetches initial state
    data = deserialize_get_devices_fixture(load_fixture("test_get_devices1.json"))
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
