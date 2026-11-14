"""Buttons (REST API): end call and reboot."""
from __future__ import annotations

from homeassistant.components.button import ButtonDeviceClass, ButtonEntity
from homeassistant.const import EntityCategory
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .coordinator import PolyConfigEntry, PolyCoordinator, PolyRestEntity
from .rest import PolyRestError


async def async_setup_entry(
    hass: HomeAssistant, entry: PolyConfigEntry, async_add_entities: AddEntitiesCallback
) -> None:
    coordinator = entry.runtime_data
    if coordinator.rest is not None:
        async_add_entities([EndCallButton(coordinator), RebootButton(coordinator)])


class EndCallButton(PolyRestEntity, ButtonEntity):
    """Hangs up every active conference."""

    _attr_name = "End call"
    _attr_icon = "mdi:phone-hangup"

    def __init__(self, coordinator: PolyCoordinator) -> None:
        super().__init__(coordinator, "end_call")

    async def async_press(self) -> None:
        try:
            await self.coordinator.rest.end_calls()
        except PolyRestError as err:
            raise HomeAssistantError(str(err)) from err
        await self.coordinator.async_request_refresh()


class RebootButton(PolyRestEntity, ButtonEntity):
    _attr_name = "Reboot"
    _attr_device_class = ButtonDeviceClass.RESTART
    _attr_entity_category = EntityCategory.CONFIG
    _attr_entity_registry_enabled_default = False

    def __init__(self, coordinator: PolyCoordinator) -> None:
        super().__init__(coordinator, "reboot")

    async def async_press(self) -> None:
        try:
            await self.coordinator.rest.reboot()
        except PolyRestError as err:
            raise HomeAssistantError(str(err)) from err
