from pytest_homeassistant_custom_component.common import MockConfigEntry
from pytest_homeassistant_custom_component.common import load_fixture
from custom_components.wundasmart.const import DOMAIN
from unittest.mock import patch
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator
from homeassistant.core import HomeAssistant
from homeassistant.components.climate import HVACAction
from .utils import deserialize_get_devices_fixture


async def test_climate(hass: HomeAssistant, config):
    entry = MockConfigEntry(domain=DOMAIN, data=config)
    entry.add_to_hass(hass)

    # Test setup of climate entity fetches initial state
    data = deserialize_get_devices_fixture(load_fixture("test_get_devices1.json"))
    with patch("custom_components.wundasmart.get_devices", return_value=data):
        await hass.config_entries.async_setup(entry.entry_id)
        await hass.async_block_till_done()

        state = hass.states.get("climate.test_room")

        assert state
        assert state.attributes["current_temperature"] == 17.8
        assert state.attributes["current_humidity"] == 66.57
        assert state.attributes["temperature"] == 0
        assert state.state == "auto"
        assert state.attributes["hvac_action"] == HVACAction.IDLE

    coordinator: DataUpdateCoordinator = hass.data[DOMAIN][entry.entry_id]
    assert coordinator

    # Test refreshing coordinator updates entity state
    data = deserialize_get_devices_fixture(load_fixture("test_get_devices2.json"))
    with patch("custom_components.wundasmart.get_devices", return_value=data):
        await coordinator.async_refresh()
        await hass.async_block_till_done()

        state = hass.states.get("climate.test_room")

        assert state
        assert state.attributes["current_temperature"] == 16.0
        assert state.attributes["temperature"] == 0
        assert state.state == "auto"
        assert state.attributes["hvac_action"] == HVACAction.PREHEATING


async def test_set_temperature(hass: HomeAssistant, config):
    entry = MockConfigEntry(domain=DOMAIN, data=config)
    entry.add_to_hass(hass)

    # Test setting temperature works
    data = deserialize_get_devices_fixture(load_fixture("test_set_temperature.json"))
    with patch("custom_components.wundasmart.get_devices", return_value=data), \
            patch("custom_components.wundasmart.climate.send_command", return_value=None) as mock:
        await hass.config_entries.async_setup(entry.entry_id)
        await hass.async_block_till_done()

        # set the temperature
        await hass.services.async_call("climate", "set_temperature", {
            "entity_id": "climate.test_room",
            "temperature": 20
        })
        await hass.async_block_till_done()

        # Check put_state was called for the right entity
        assert mock.call_count == 1
        assert mock.call_args.kwargs["params"]
        assert mock.call_args.kwargs["params"]["roomid"] == 121

        # Check the state was updated
        state = hass.states.get("climate.test_room")
        assert state
        assert state.attributes["current_temperature"] == 16.0
        assert state.attributes["temperature"] == 20
        assert state.state == "heat"
        assert state.attributes["hvac_action"] == HVACAction.IDLE


async def test_trvs_only(hass: HomeAssistant, config):
    entry = MockConfigEntry(domain=DOMAIN, data=config)
    entry.add_to_hass(hass)

    # Rooms with TRVs only and no sensor should still get a temperature reading
    data = deserialize_get_devices_fixture(load_fixture("test_trvs_only.json"))
    with patch("custom_components.wundasmart.get_devices", return_value=data):
        await hass.config_entries.async_setup(entry.entry_id)
        await hass.async_block_till_done()

        state = hass.states.get("climate.test_room")

        assert state
        assert state.attributes["current_temperature"] == 15.5
        assert "current_humidity" not in state.attributes


async def test_hvac_mode_when_manually_turned_off(hass: HomeAssistant, config):
    entry = MockConfigEntry(domain=DOMAIN, data=config)
    entry.add_to_hass(hass)

    data = deserialize_get_devices_fixture(load_fixture("test_manual_off.json"))
    with patch("custom_components.wundasmart.get_devices", return_value=data):
        await hass.config_entries.async_setup(entry.entry_id)
        await hass.async_block_till_done()

        state = hass.states.get("climate.test_room")

        assert state
        assert state.state == HVACAction.OFF
        assert state.attributes["hvac_action"] == HVACAction.OFF


async def test_set_presets(hass: HomeAssistant, config):
    entry = MockConfigEntry(domain=DOMAIN, data=config)
    entry.add_to_hass(hass)

    data = deserialize_get_devices_fixture(load_fixture("test_set_presets.json"))
    with patch("custom_components.wundasmart.get_devices", return_value=data), \
            patch("custom_components.wundasmart.climate.send_command", return_value=None) as mock:
        await hass.config_entries.async_setup(entry.entry_id)
        await hass.async_block_till_done()

        state = hass.states.get("climate.test_room")

        assert state
        assert state.attributes["temperature"] == 21.0
        assert state.attributes["preset_mode"] == "comfort"

        # set the preset 'reduced'
        await hass.services.async_call("climate", "set_preset_mode", {
            "entity_id": "climate.test_room",
            "preset_mode": "reduced"
        })
        await hass.async_block_till_done()

        # Check send_command was called correctly
        assert mock.call_count == 1
        assert mock.call_args.kwargs["params"]
        assert mock.call_args.kwargs["params"]["roomid"] == 121
        assert mock.call_args.kwargs["params"]["temp"] == 14.0

        # set the preset 'eco'
        await hass.services.async_call("climate", "set_preset_mode", {
            "entity_id": "climate.test_room",
            "preset_mode": "eco"
        })
        await hass.async_block_till_done()

        # Check send_command was called correctly
        assert mock.call_count == 2
        assert mock.call_args.kwargs["params"]
        assert mock.call_args.kwargs["params"]["roomid"] == 121
        assert mock.call_args.kwargs["params"]["temp"] == 19.0

        # set the preset 'comfort'
        await hass.services.async_call("climate", "set_preset_mode", {
            "entity_id": "climate.test_room",
            "preset_mode": "comfort"
        })
        await hass.async_block_till_done()

        # Check send_command was called correctly
        assert mock.call_count == 3
        assert mock.call_args.kwargs["params"]
        assert mock.call_args.kwargs["params"]["roomid"] == 121
        assert mock.call_args.kwargs["params"]["temp"] == 21.0


async def test_turn_on_off(hass: HomeAssistant, config):
    entry = MockConfigEntry(domain=DOMAIN, data=config)
    entry.add_to_hass(hass)

    data = deserialize_get_devices_fixture(load_fixture("test_manual_off.json"))
    with patch("custom_components.wundasmart.get_devices", return_value=data):
        await hass.config_entries.async_setup(entry.entry_id)
        await hass.async_block_till_done()

        state = hass.states.get("climate.test_room")

        assert state
        assert state.state == HVACAction.OFF
        assert state.attributes["hvac_action"] == HVACAction.OFF
        temp = state.attributes["temperature"]

        with patch("custom_components.wundasmart.climate.send_command", return_value=None) as mock:
            await hass.services.async_call("climate", "turn_on", {
                "entity_id": "climate.test_room"
            })
            await hass.async_block_till_done()

            # Check send_command was called correctly
            assert mock.call_count == 1
            assert mock.call_args.kwargs["params"]
            assert mock.call_args.kwargs["params"]["roomid"] == 121
            assert mock.call_args.kwargs["params"]["temp"] == 21

        with patch("custom_components.wundasmart.climate.send_command", return_value=None) as mock:
            await hass.services.async_call("climate", "turn_off", {
                "entity_id": "climate.test_room"
            })
            await hass.async_block_till_done()

            # Check send_command was called correctly
            assert mock.call_count == 1
            assert mock.call_args.kwargs["params"]
            assert mock.call_args.kwargs["params"]["roomid"] == 121
            assert mock.call_args.kwargs["params"]["temp"] == 0
