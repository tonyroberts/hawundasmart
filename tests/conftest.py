"""Fixtures for testing."""
from homeassistant.const import CONF_HOST, CONF_USERNAME, CONF_PASSWORD
import pytest
import sys


if sys.platform == "win32":
    # Allow sockets on Windows otherwise asyncio doesn't work
    import pytest_socket
    pytest_socket.disable_socket = lambda *args, **kwargs: None


@pytest.fixture(autouse=True)
def auto_enable_custom_integrations(enable_custom_integrations):
    yield


@pytest.fixture
def config(enable_custom_integrations):
    # pywundatest functions are mocked so no real host is needed
    return {
        CONF_HOST: "none",
        CONF_USERNAME: "root",
        CONF_PASSWORD: "password"
    }
