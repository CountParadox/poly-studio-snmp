"""Number (REST API): speaker volume."""
from __future__ import annotations

from homeassistant.components.number import NumberEntity, NumberMode
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
        async_add_entities([VolumeNumber(coordinator)])


class VolumeNumber(PolyRestEntity, NumberEntity):
    _attr_name = "Volume"
    _attr_icon = "mdi:volume-high"
    _attr_native_min_value = 0
    _attr_native_max_value = 100
    _attr_native_step = 1
    _attr_mode = NumberMode.SLIDER

    def __init__(self, coordinator: PolyCoordinator) -> None:
        super().__init__(coordinator, "volume")

    @property
    def native_value(self) -> float | None:
        return (self.rest_data.get("audio") or {}).get("volume")

    async def async_set_native_value(self, value: float) -> None:
        try:
            await self.coordinator.rest.set_volume(int(value))
        except PolyRestError as err:
            raise HomeAssistantError(str(err)) from err
        await self.coordinator.async_request_refresh()
