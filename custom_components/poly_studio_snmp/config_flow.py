"""Config flow for Poly Studio SNMP."""
from __future__ import annotations

from typing import Any

import voluptuous as vol

from homeassistant.config_entries import ConfigFlow, ConfigFlowResult
from homeassistant.const import CONF_HOST, CONF_PORT

from .const import CONF_COMMUNITY, DEFAULT_COMMUNITY, DEFAULT_PORT, DOMAIN
from .snmp import SnmpError, fetch

SCHEMA = vol.Schema(
    {
        vol.Required(CONF_HOST): str,
        vol.Required(CONF_PORT, default=DEFAULT_PORT): vol.All(int, vol.Range(min=1, max=65535)),
        vol.Required(CONF_COMMUNITY, default=DEFAULT_COMMUNITY): str,
    }
)


class PolyConfigFlow(ConfigFlow, domain=DOMAIN):
    """Set up a Poly video bar by host and SNMP v2c community."""

    VERSION = 1

    async def async_step_user(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        errors: dict[str, str] = {}
        if user_input is not None:
            try:
                data = await self.hass.async_add_executor_job(
                    fetch, user_input[CONF_HOST], user_input[CONF_PORT], user_input[CONF_COMMUNITY]
                )
            except SnmpError:
                errors["base"] = "cannot_connect"
            else:
                await self.async_set_unique_id(data.get("1.5.0"))
                self._abort_if_unique_id_configured(updates={CONF_HOST: user_input[CONF_HOST]})
                title = data.sys_name or data.get("1.4.0") or user_input[CONF_HOST]
                return self.async_create_entry(title=title, data=user_input)
        return self.async_show_form(
            step_id="user",
            data_schema=self.add_suggested_values_to_schema(SCHEMA, user_input),
            errors=errors,
        )
