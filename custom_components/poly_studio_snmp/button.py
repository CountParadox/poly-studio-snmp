"""Buttons (REST API): answer, end call, join meeting and reboot."""
from __future__ import annotations

from collections.abc import Awaitable, Callable
from dataclasses import dataclass

from homeassistant.components.button import (
    ButtonDeviceClass,
    ButtonEntity,
    ButtonEntityDescription,
)
from homeassistant.const import EntityCategory
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from . import next_joinable_meeting
from .coordinator import PolyConfigEntry, PolyCoordinator, PolyRestEntity
from .rest import PolyRestError


@dataclass(frozen=True, kw_only=True)
class PolyButtonDescription(ButtonEntityDescription):
    press_fn: Callable[[PolyCoordinator], Awaitable[None]]
    refresh: bool = True


async def _join(coordinator: PolyCoordinator) -> None:
    meeting = next_joinable_meeting(coordinator)
    if meeting is None:
        raise PolyRestError("there is no joinable meeting on the calendar")
    await coordinator.rest.join_meeting(meeting["id"])


DESCRIPTIONS = (
    PolyButtonDescription(
        key="answer_call", name="Answer call", icon="mdi:phone-incoming",
        press_fn=lambda c: c.rest.answer(),
    ),
    PolyButtonDescription(
        key="end_call", name="End call", icon="mdi:phone-hangup",
        press_fn=lambda c: c.rest.end_calls(),
    ),
    PolyButtonDescription(
        key="join_meeting", name="Join meeting", icon="mdi:calendar-arrow-right", press_fn=_join,
    ),
    PolyButtonDescription(
        key="reboot", name="Reboot", device_class=ButtonDeviceClass.RESTART,
        entity_category=EntityCategory.CONFIG, entity_registry_enabled_default=False,
        press_fn=lambda c: c.rest.reboot(), refresh=False,
    ),
)


async def async_setup_entry(
    hass: HomeAssistant, entry: PolyConfigEntry, async_add_entities: AddEntitiesCallback
) -> None:
    coordinator = entry.runtime_data
    if coordinator.rest is not None:
        async_add_entities(PolyButton(coordinator, d) for d in DESCRIPTIONS)


class PolyButton(PolyRestEntity, ButtonEntity):
    entity_description: PolyButtonDescription

    def __init__(self, coordinator: PolyCoordinator, description: PolyButtonDescription) -> None:
        super().__init__(coordinator, description.key)
        self.entity_description = description

    async def async_press(self) -> None:
        try:
            await self.entity_description.press_fn(self.coordinator)
        except PolyRestError as err:
            raise HomeAssistantError(str(err)) from err
        if self.entity_description.refresh:
            await self.coordinator.async_request_refresh()
