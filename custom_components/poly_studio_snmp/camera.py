"""Camera (REST API): still snapshots from /rest/cameras/snapshot/<id>."""
from __future__ import annotations

import logging

from homeassistant.components.camera import Camera
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .coordinator import PolyConfigEntry, PolyCoordinator, PolyRestEntity
from .rest import PolyRestError

_LOGGER = logging.getLogger(__name__)

# key -> (name, enabled by default)
SNAPSHOTS = {
    "near": ("Camera snapshot", True),
    "far": ("Far end snapshot", False),
    "content": ("Content snapshot", False),
}


async def async_setup_entry(
    hass: HomeAssistant, entry: PolyConfigEntry, async_add_entities: AddEntitiesCallback
) -> None:
    coordinator = entry.runtime_data
    if coordinator.rest is not None:
        async_add_entities(PolySnapshotCamera(coordinator, which) for which in SNAPSHOTS)


class PolySnapshotCamera(PolyRestEntity, Camera):
    def __init__(self, coordinator: PolyCoordinator, which: str) -> None:
        PolyRestEntity.__init__(self, coordinator, f"snapshot_{which}")
        Camera.__init__(self)
        self._which = which
        self._attr_name, self._attr_entity_registry_enabled_default = SNAPSHOTS[which]
        self.content_type = "image/jpeg"

    async def async_camera_image(
        self, width: int | None = None, height: int | None = None
    ) -> bytes | None:
        try:
            image = await self.coordinator.rest.snapshot(self._which)
        except PolyRestError as err:
            _LOGGER.debug("snapshot %s: %s", self._which, err)
            return None
        # A JPEG starts with FF D8; anything else is an error body, not an image.
        return image if image[:2] == b"\xff\xd8" else None
