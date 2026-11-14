"""Poly Studio video bar monitoring over SNMP, with optional REST controls."""
from __future__ import annotations

import voluptuous as vol

from homeassistant.config_entries import ConfigEntryState
from homeassistant.const import ATTR_DEVICE_ID, Platform
from homeassistant.core import HomeAssistant, ServiceCall
from homeassistant.exceptions import HomeAssistantError, ServiceValidationError
from homeassistant.helpers import config_validation as cv, device_registry as dr
from homeassistant.helpers.typing import ConfigType

from .const import DOMAIN
from .coordinator import PolyConfigEntry, PolyCoordinator
from .rest import PolyRestError

PLATFORMS = [
    Platform.BINARY_SENSOR,
    Platform.BUTTON,
    Platform.CALENDAR,
    Platform.CAMERA,
    Platform.NUMBER,
    Platform.SELECT,
    Platform.SENSOR,
    Platform.SWITCH,
]

CONFIG_SCHEMA = cv.config_entry_only_config_schema(DOMAIN)

DIAL_TYPES = ["AUTO", "VIDEO", "VOICE", "SIP", "H323", "VOICE_SIP", "VOICE_H323"]
_DEVICE = {vol.Optional(ATTR_DEVICE_ID): cv.string}

SERVICES: dict[str, vol.Schema] = {
    "dial": vol.Schema(
        {
            **_DEVICE,
            vol.Required("address"): cv.string,
            vol.Optional("dial_type", default="AUTO"): vol.In(DIAL_TYPES),
            vol.Optional("rate"): vol.All(vol.Coerce(int), vol.Range(min=64, max=6144)),
            vol.Optional("password"): cv.string,
        }
    ),
    "send_dtmf": vol.Schema(
        {**_DEVICE, vol.Required("digits"): vol.All(cv.string, vol.Match(r"^[0-9*#,]+$"))}
    ),
    "join_meeting": vol.Schema({**_DEVICE, vol.Optional("meeting_id"): cv.string}),
    "recall_preset": vol.Schema(
        {**_DEVICE, vol.Required("preset"): vol.All(vol.Coerce(int), vol.Range(min=0, max=99))}
    ),
    "store_preset": vol.Schema(
        {**_DEVICE, vol.Required("preset"): vol.All(vol.Coerce(int), vol.Range(min=0, max=99))}
    ),
}


def _targets(hass: HomeAssistant, call: ServiceCall) -> list[PolyCoordinator]:
    entries = [
        e for e in hass.config_entries.async_entries(DOMAIN) if e.state is ConfigEntryState.LOADED
    ]
    if device_id := call.data.get(ATTR_DEVICE_ID):
        device = dr.async_get(hass).async_get(device_id)
        ids = device.config_entries if device else set()
        entries = [e for e in entries if e.entry_id in ids]
    coordinators = [e.runtime_data for e in entries if e.runtime_data.rest is not None]
    if not coordinators:
        raise ServiceValidationError(
            "No Poly device with a configured admin login matches this action"
        )
    return coordinators


def next_joinable_meeting(coordinator: PolyCoordinator) -> dict | None:
    """Current or next upcoming meeting the device can dial."""
    meetings = [
        m for m in (coordinator.data.rest or {}).get("meetings") or []
        if m.get("id") and m.get("canDial", True) and not m.get("canceled")
    ]
    return min(meetings, key=lambda m: m.get("startTime") or 0) if meetings else None


async def async_setup(hass: HomeAssistant, config: ConfigType) -> bool:
    async def handle(call: ServiceCall) -> None:
        for coordinator in _targets(hass, call):
            rest = coordinator.rest
            try:
                if call.service == "dial":
                    await rest.dial(
                        call.data["address"], call.data["dial_type"],
                        call.data.get("rate"), call.data.get("password"),
                    )
                elif call.service == "send_dtmf":
                    await rest.send_dtmf(call.data["digits"])
                elif call.service == "join_meeting":
                    meeting_id = call.data.get("meeting_id")
                    if not meeting_id:
                        meeting = next_joinable_meeting(coordinator)
                        if meeting is None:
                            raise ServiceValidationError("No joinable meeting on the calendar")
                        meeting_id = meeting["id"]
                    await rest.join_meeting(meeting_id)
                elif call.service == "recall_preset":
                    await rest.preset(call.data["preset"], "activate")
                elif call.service == "store_preset":
                    await rest.preset(call.data["preset"], "store")
            except PolyRestError as err:
                raise HomeAssistantError(str(err)) from err
            await coordinator.async_request_refresh()

    for name, schema in SERVICES.items():
        hass.services.async_register(DOMAIN, name, handle, schema=schema)
    return True


async def async_setup_entry(hass: HomeAssistant, entry: PolyConfigEntry) -> bool:
    coordinator = PolyCoordinator(hass, entry)
    await coordinator.async_config_entry_first_refresh()
    entry.runtime_data = coordinator
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    return True


async def async_unload_entry(hass: HomeAssistant, entry: PolyConfigEntry) -> bool:
    return await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
