"""Config flow to configure Wundasmart."""
import voluptuous as vol
from typing import Any

from homeassistant import config_entries, core, exceptions
from homeassistant.const import CONF_HOST, CONF_USERNAME, CONF_PASSWORD, CONF_SCAN_INTERVAL
from homeassistant.data_entry_flow import FlowResult
from homeassistant.core import callback

from .const import *
from .session import get_session
from .pywundasmart import get_devices

STEP_USER_DATA_SCHEMA = vol.Schema(
    {
        vol.Required(CONF_HOST): str,
        vol.Required(CONF_USERNAME, default="root"): str,
        vol.Required(CONF_PASSWORD, default="root"): str
    }
)


class Hub:
    """Wundasmart Hub class."""

    def __init__(self, hass, wunda_ip, wunda_user, wunda_pass):
        """Wundasmart Hub class init."""
        self._hass = hass
        self._wunda_ip = wunda_ip
        self._wunda_user = wunda_user
        self._wunda_pass = wunda_pass

    async def authenticate(self):
        """Wundasmart Hub class authenticate."""
        async with get_session() as session:
            return await get_devices(
                session,
                self._wunda_ip,
                self._wunda_user,
                self._wunda_pass,
            )


async def validate_input(hass: core.HomeAssistant, wunda_ip, wunda_user, wunda_pass):
    """Validate api key."""
    hub = Hub(hass, wunda_ip, wunda_user, wunda_pass)
    result = await hub.authenticate()
    if result["state"] is False:
        if result["code"] == -201:
            raise InvalidAuth
        if result["code"] == -200:
            raise CannotConnect


class ConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Handle a config flow."""

    VERSION = 1

    @staticmethod
    @callback
    def async_get_options_flow(config_entry: config_entries.ConfigEntry) -> config_entries.OptionsFlow:
        """Get the options flow for this handler."""
        return OptionsFlow(config_entry)

    async def async_step_user(self, user_input=None):
        """Show the setup form to the user."""
        if user_input is None:
            return self.async_show_form(
                step_id="user", data_schema=STEP_USER_DATA_SCHEMA
            )

        errors = {}

        try:
            await validate_input(
                self.hass,
                user_input[CONF_HOST],
                user_input[CONF_USERNAME],
                user_input[CONF_PASSWORD]
            )
        except CannotConnect:
            errors["base"] = "cannot_connect"
        except InvalidAuth:
            errors["base"] = "invalid_auth"
        else:
            return self.async_create_entry(title="Wundasmart", data=user_input)

        return self.async_show_form(
            step_id="user", data_schema=STEP_USER_DATA_SCHEMA, errors=errors
        )


class OptionsFlow(config_entries.OptionsFlow):

    def __init__(self, config_entry: config_entries.ConfigEntry) -> None:
        self.config_entry = config_entry

    async def async_step_init(self, user_input: dict[str, Any] | None = None) -> FlowResult:
        if user_input is not None:
            return self.async_create_entry(title="", data=user_input)

        options = {
            vol.Optional(
                CONF_SCAN_INTERVAL,
                default=self.config_entry.options.get(
                    CONF_SCAN_INTERVAL, DEFAULT_SCAN_INTERVAL
                )): int,
            vol.Optional(
                CONF_CONNECT_TIMEOUT,
                default=self.config_entry.options.get(
                    CONF_CONNECT_TIMEOUT, DEFAULT_CONNECT_TIMEOUT
                )): int,
            vol.Optional(
                CONF_READ_TIMEOUT,
                default=self.config_entry.options.get(
                    CONF_READ_TIMEOUT, DEFAULT_READ_TIMEOUT
                )): int
        }

        return self.async_show_form(step_id="init", data_schema=vol.Schema(options))


class CannotConnect(exceptions.HomeAssistantError):
    """Error to indicate we cannot connect."""


class InvalidAuth(exceptions.HomeAssistantError):
    """Error to indicate there is invalid auth."""
