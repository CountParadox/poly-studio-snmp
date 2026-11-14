"""Switches (REST API): microphone mute, camera (local video) mute, digital signage."""
from __future__ import annotations

from typing import Any

from homeassistant.components.switch import SwitchEntity
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
        async_add_entities(
            [MicMuteSwitch(coordinator), VideoMuteSwitch(coordinator), SignageSwitch(coordinator)]
        )


class _MuteSwitch(PolyRestEntity, SwitchEntity):
    async def _set(self, muted: bool) -> None:
        raise NotImplementedError

    async def _apply(self, muted: bool) -> None:
        try:
            await self._set(muted)
        except PolyRestError as err:
            raise HomeAssistantError(str(err)) from err
        await self.coordinator.async_request_refresh()

    async def async_turn_on(self, **kwargs: Any) -> None:
        await self._apply(True)

    async def async_turn_off(self, **kwargs: Any) -> None:
        await self._apply(False)


class MicMuteSwitch(_MuteSwitch):
    _attr_name = "Microphone mute"
    _attr_icon = "mdi:microphone-off"

    def __init__(self, coordinator: PolyCoordinator) -> None:
        super().__init__(coordinator, "mic_mute")

    @property
    def is_on(self) -> bool | None:
        return (self.rest_data.get("audio") or {}).get("muted")

    async def _set(self, muted: bool) -> None:
        await self.coordinator.rest.set_mic_mute(muted)


class VideoMuteSwitch(_MuteSwitch):
    _attr_name = "Camera mute"
    _attr_icon = "mdi:video-off"

    def __init__(self, coordinator: PolyCoordinator) -> None:
        super().__init__(coordinator, "video_mute")

    @property
    def is_on(self) -> bool | None:
        return self.rest_data.get("video_muted")

    async def _set(self, muted: bool) -> None:
        await self.coordinator.rest.set_video_mute(muted)


class SignageSwitch(_MuteSwitch):
    """Starts or stops the Digital Signage application."""

    _attr_name = "Digital signage"
    _attr_icon = "mdi:television-play"

    def __init__(self, coordinator: PolyCoordinator) -> None:
        super().__init__(coordinator, "signage")

    @property
    def is_on(self) -> bool | None:
        return self.rest_data.get("signage")

    async def _set(self, muted: bool) -> None:
        await self.coordinator.rest.set_signage(muted)
