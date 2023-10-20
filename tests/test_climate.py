from pytest_homeassistant_custom_component.common import MockConfigEntry
from pytest_homeassistant_custom_component.common import load_fixture
from custom_components.wundersmart.const import DOMAIN
from unittest.mock import patch


async def test_climate(hass, config):
    entry = MockConfigEntry(domain=DOMAIN, data=config)
    entry.add_to_hass(hass)

    # Test setup of climate entity fetches initial state
    data = json.loads(load_fixture("test_get_devices1.json"))
    with patch("custom_components.wundersmart.get_devices", return_value=data):
        await hass.config_entries.async_setup(entry.entry_id)
        await hass.async_block_till_done()

        state = hass.states.get("climate.test_room")

        assert state
        assert state.attributes["current_temperature"] == 17.8
