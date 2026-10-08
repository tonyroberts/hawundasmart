from pytest_homeassistant_custom_component.common import MockConfigEntry
from pytest_homeassistant_custom_component.common import load_fixture
from custom_components.wundasmart.const import DOMAIN
from unittest.mock import patch
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator
from homeassistant.core import HomeAssistant
from homeassistant.components.climate import HVACAction, HVACMode
import pytest
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


@pytest.mark.parametrize("temp_pre, expected_mode", [
    ("0", HVACMode.AUTO),
    ("17", HVACMode.HEAT),
    ("20", HVACMode.OFF),
    ("128", HVACMode.AUTO),
])
async def test_hvac_action_flags(hass: HomeAssistant, config, temp_pre, expected_mode):
    """Room demand controls action through heating and idle transitions."""
    entry = MockConfigEntry(domain=DOMAIN, data=config)
    entry.add_to_hass(hass)
    data = deserialize_get_devices_fixture(load_fixture("test_set_temperature.json"))
    room = next(device for device in data["devices"].values()
                if device.get("device_type") == "ROOM")
    room["state"]["temp_pre"] = temp_pre

    with patch("custom_components.wundasmart.get_devices", return_value=data):
        await hass.config_entries.async_setup(entry.entry_id)
        await hass.async_block_till_done()
        coordinator = hass.data[DOMAIN][entry.entry_id]

        # Repeat the cycle to catch stale action state. Bit 0x04 must not matter.
        for heat, active in (("6", True), ("7", True), ("5", False), ("4", False),
                             ("2", True), ("3", True), ("1", False), ("0", False),
                             ("6", True), ("4", False)):
            room["state"]["heat"] = heat
            await coordinator.async_refresh()
            await hass.async_block_till_done()
            state = hass.states.get("climate.test_room")
            assert state
            assert state.state == expected_mode
            if expected_mode == HVACMode.OFF:
                expected_action = HVACAction.OFF
            elif active:
                expected_action = (HVACAction.PREHEATING if temp_pre == "128"
                                   else HVACAction.HEATING)
            else:
                expected_action = HVACAction.IDLE
            assert state.attributes["hvac_action"] == expected_action


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
        assert state.attributes["hvac_action"] == HVACAction.HEATING


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


async def test_set_preset_temps(hass: HomeAssistant, config):
    entry = MockConfigEntry(domain=DOMAIN, data=config)
    entry.add_to_hass(hass)

    data = deserialize_get_devices_fixture(load_fixture("test_set_presets.json"))
    with patch("custom_components.wundasmart.get_devices", return_value=data), \
            patch("custom_components.wundasmart.climate.send_command", return_value=None) as mock:
        await hass.config_entries.async_setup(entry.entry_id)
        await hass.async_block_till_done()

        with patch("custom_components.wundasmart.climate.set_register", return_value=None) as mock:
            await hass.services.async_call("wundasmart", "set_preset_temperature", {
                "entity_id": "climate.test_room",
                "preset": "eco",
                "temperature": 10
            })
            await hass.async_block_till_done()

            # Check send_command was called correctly
            assert mock.call_count == 1
            assert mock.call_args.kwargs["device_id"] == 121
            assert mock.call_args.kwargs["register_id"] == "t_norm"
            assert mock.call_args.kwargs["value"] == 10

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
