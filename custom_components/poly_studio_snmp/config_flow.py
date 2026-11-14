"""Config flow for Poly Studio SNMP."""
from __future__ import annotations

from typing import Any

import voluptuous as vol

from homeassistant.config_entries import ConfigFlow, ConfigFlowResult
from homeassistant.const import CONF_HOST, CONF_PASSWORD, CONF_PORT, CONF_USERNAME
from homeassistant.helpers.selector import (
    TextSelector,
    TextSelectorConfig,
    TextSelectorType,
)

from .const import CONF_COMMUNITY, DEFAULT_COMMUNITY, DEFAULT_PORT, DOMAIN
from .coordinator import create_rest
from .rest import PolyRestAuthError, PolyRestError
from .snmp import PolyData, SnmpError, fetch

SCHEMA = vol.Schema(
    {
        vol.Required(CONF_HOST): str,
        vol.Required(CONF_PORT, default=DEFAULT_PORT): vol.All(int, vol.Range(min=1, max=65535)),
        vol.Required(CONF_COMMUNITY, default=DEFAULT_COMMUNITY): str,
        vol.Optional(CONF_USERNAME, default="admin"): str,
        vol.Optional(CONF_PASSWORD): TextSelector(
            TextSelectorConfig(type=TextSelectorType.PASSWORD)
        ),
    }
)


class PolyConfigFlow(ConfigFlow, domain=DOMAIN):
    """Set up a Poly video bar: SNMP v2c, plus an optional admin login for REST controls."""

    VERSION = 1

    async def _validate(self, user_input: dict[str, Any], errors: dict[str, str]) -> PolyData | None:
        try:
            data = await self.hass.async_add_executor_job(
                fetch, user_input[CONF_HOST], user_input[CONF_PORT], user_input[CONF_COMMUNITY]
            )
        except SnmpError:
            errors["base"] = "cannot_connect"
            return None
        if user_input.get(CONF_PASSWORD):
            rest = create_rest(
                self.hass, user_input[CONF_HOST], user_input.get(CONF_USERNAME) or "admin",
                user_input[CONF_PASSWORD],
            )
            try:
                await rest.login()
            except PolyRestAuthError:
                errors["base"] = "invalid_auth"
                return None
            except PolyRestError:
                errors["base"] = "rest_cannot_connect"
                return None
        return data

    async def async_step_user(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        errors: dict[str, str] = {}
        if user_input is not None:
            data = await self._validate(user_input, errors)
            if data is not None:
                await self.async_set_unique_id(data.get("1.5.0"))
                self._abort_if_unique_id_configured(updates={CONF_HOST: user_input[CONF_HOST]})
                title = data.sys_name or data.get("1.4.0") or user_input[CONF_HOST]
                return self.async_create_entry(title=title, data=user_input)
        return self.async_show_form(
            step_id="user",
            data_schema=self.add_suggested_values_to_schema(SCHEMA, user_input),
            errors=errors,
        )

    async def async_step_reconfigure(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Change host, community or the REST login of an existing entry."""
        entry = self._get_reconfigure_entry()
        errors: dict[str, str] = {}
        if user_input is not None:
            data = await self._validate(user_input, errors)
            if data is not None:
                await self.async_set_unique_id(data.get("1.5.0"))
                self._abort_if_unique_id_mismatch()
                return self.async_update_reload_and_abort(entry, data=user_input)
        suggested = user_input or {k: v for k, v in entry.data.items() if k != CONF_PASSWORD}
        return self.async_show_form(
            step_id="reconfigure",
            data_schema=self.add_suggested_values_to_schema(SCHEMA, suggested),
            errors=errors,
        )
