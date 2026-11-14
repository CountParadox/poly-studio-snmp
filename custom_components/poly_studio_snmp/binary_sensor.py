"""Binary sensors for Poly Studio SNMP."""
from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass

from homeassistant.components.binary_sensor import (
    BinarySensorEntity,
    BinarySensorEntityDescription,
)
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .coordinator import PolyConfigEntry, PolyEntity
from .snmp import PolyData


@dataclass(frozen=True, kw_only=True)
class PolyBinaryDescription(BinarySensorEntityDescription):
    value_fn: Callable[[PolyData], bool | None]


def _in_call(data: PolyData) -> bool:
    # conferenceNumberActiveConferences > 0, or any row in callActiveCallsTable
    return bool(data.get("5.1.0")) or bool(data.call_indexes)


def _sending_content(data: PolyData) -> bool | None:
    value = data.call(63)  # callActiveCallsSendingContent, TruthValue
    return None if value is None else value == 1


def _device_mode(data: PolyData) -> bool | None:
    # REST /rest/system/mode/device: the bar is being used as a USB camera/speakerphone
    return (data.rest or {}).get("device_mode")


REST_DESCRIPTIONS = (
    PolyBinaryDescription(
        key="device_mode", name="USB device mode", icon="mdi:usb", value_fn=_device_mode
    ),
)

DESCRIPTIONS = (
    PolyBinaryDescription(key="in_call", name="In call", icon="mdi:video", value_fn=_in_call),
    PolyBinaryDescription(
        key="sending_content", name="Sending content", icon="mdi:monitor-share",
        value_fn=_sending_content,
    ),
)


async def async_setup_entry(
    hass: HomeAssistant, entry: PolyConfigEntry, async_add_entities: AddEntitiesCallback
) -> None:
    coordinator = entry.runtime_data
    descriptions = DESCRIPTIONS + (REST_DESCRIPTIONS if coordinator.rest is not None else ())
    async_add_entities(PolyBinarySensor(coordinator, d) for d in descriptions)


class PolyBinarySensor(PolyEntity, BinarySensorEntity):
    entity_description: PolyBinaryDescription

    def __init__(self, coordinator, description: PolyBinaryDescription) -> None:
        super().__init__(coordinator, description.key)
        self.entity_description = description

    @property
    def is_on(self) -> bool | None:
        return self.entity_description.value_fn(self.coordinator.data)
