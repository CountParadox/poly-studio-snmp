"""Select (REST API): recall a stored camera preset."""
from __future__ import annotations

from homeassistant.components.select import SelectEntity
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
        async_add_entities([PresetSelect(coordinator)])


class PresetSelect(PolyRestEntity, SelectEntity):
    """Lists the presets stored on the device; choosing one moves the camera there.

    The device does not report which preset is active, so the state is the last one
    chosen here.
    """

    _attr_name = "Camera preset"
    _attr_icon = "mdi:camera-marker"

    def __init__(self, coordinator: PolyCoordinator) -> None:
        super().__init__(coordinator, "camera_preset")
        self._last: str | None = None

    @property
    def options(self) -> list[str]:
        presets = self.rest_data.get("presets") or []
        return [
            str(p["index"]) for p in sorted(presets, key=lambda p: p.get("index", 0))
            if p.get("stored") and p.get("index") is not None
        ]

    @property
    def current_option(self) -> str | None:
        return self._last if self._last in self.options else None

    async def async_select_option(self, option: str) -> None:
        try:
            await self.coordinator.rest.preset(int(option), "activate")
        except PolyRestError as err:
            raise HomeAssistantError(str(err)) from err
        self._last = option
        self.async_write_ha_state()
