"""Sensors for Poly Studio SNMP.

OID suffixes are relative to 1.3.6.1.4.1.13885.101.1 (polycom-endpointObjects).
Call sensors read the first row of callActiveCallsTable and are unknown when idle.
Units are inferred from observation; the MIB declares none.
"""
from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorEntityDescription,
    SensorStateClass,
)
from homeassistant.const import PERCENTAGE, EntityCategory, UnitOfDataRate, UnitOfTime
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import STATUS_MAP, STATUS_OPTIONS
from .coordinator import PolyConfigEntry, PolyEntity
from .snmp import PolyData

MS = UnitOfTime.MILLISECONDS
KBPS = UnitOfDataRate.KILOBITS_PER_SECOND
MEASUREMENT = SensorStateClass.MEASUREMENT
DIAGNOSTIC = EntityCategory.DIAGNOSTIC


@dataclass(frozen=True, kw_only=True)
class PolySensorDescription(SensorEntityDescription):
    value_fn: Callable[[PolyData], Any]
    # Only create the entity if the device returned this OID suffix at setup.
    requires: str | None = None


def _status(key: str, name: str, suffix: str, enabled: bool = True) -> PolySensorDescription:
    return PolySensorDescription(
        key=key,
        name=name,
        device_class=SensorDeviceClass.ENUM,
        options=STATUS_OPTIONS,
        entity_category=DIAGNOSTIC,
        entity_registry_enabled_default=enabled,
        requires=suffix,
        value_fn=lambda d: STATUS_MAP.get(d.get(suffix)),
    )


def _call_num(key: str, name: str, column: int, unit: str | None = None,
              device_class: SensorDeviceClass | None = None,
              state_class: SensorStateClass = MEASUREMENT,
              enabled: bool = True, icon: str | None = None) -> PolySensorDescription:
    return PolySensorDescription(
        key=key, name=name, native_unit_of_measurement=unit, device_class=device_class,
        state_class=state_class, entity_registry_enabled_default=enabled, icon=icon,
        value_fn=lambda d: d.call(column),
    )


def _call_text(key: str, name: str, column: int, icon: str | None = None,
               enabled: bool = True) -> PolySensorDescription:
    return PolySensorDescription(
        key=key, name=name, icon=icon, entity_registry_enabled_default=enabled,
        value_fn=lambda d: d.call(column),
    )


def _call_fps(column: int) -> Callable[[PolyData], int | None]:
    def fn(d: PolyData) -> int | None:
        value = d.call(column)
        return int(value) if isinstance(value, str) and value.isdigit() else None
    return fn


RATE = SensorDeviceClass.DATA_RATE
TOTAL = SensorStateClass.TOTAL_INCREASING

DESCRIPTIONS: tuple[PolySensorDescription, ...] = (
    # --- status (disabled / ok / failed) ---
    _status("status", "Status", "1.6.0"),
    _status("hardware_status", "Hardware status", "3.1.0"),
    _status("sip_status", "SIP status", "2.8.1.0"),
    _status("sip_registration_status", "SIP registration", "2.8.3.1.2.1"),
    _status("sip_proxy_status", "SIP proxy", "2.8.2.1.2.1", enabled=False),
    _status("h323_status", "H.323 status", "2.7.1.0", enabled=False),
    _status("h323_registration_status", "H.323 registration", "2.7.2.0", enabled=False),
    _status("camera_status", "Camera status", "3.6.1.0"),
    _status("microphone_status", "Microphone status", "3.5.1.0"),
    _status("nic_status", "Network interface status", "3.10.1.0"),
    _status("external_integration_status", "External integration status", "6.1.0"),
    _status("presence_status", "Presence status", "6.7.1.0", enabled=False),
    _status("cdr_status", "CDR status", "6.8.1.0", enabled=False),
    _status("syslog_status", "Syslog status", "6.9.1.0", enabled=False),
    _status("software_update_status", "Software update status", "6.10.1.0", enabled=False),
    _status("provisioning_status", "Provisioning status", "6.11.1.0", enabled=False),
    _status("exchange_status", "Calendar status", "6.12.1.0", enabled=False),
    _status("directory_status", "Directory status", "6.13.1.0", enabled=False),
    # --- device ---
    PolySensorDescription(
        key="nic_speed", name="Network link speed", requires="3.10.2.1.4.1",
        native_unit_of_measurement=UnitOfDataRate.MEGABITS_PER_SECOND, device_class=RATE,
        entity_category=DIAGNOSTIC, value_fn=lambda d: d.get("3.10.2.1.4.1"),
    ),
    PolySensorDescription(
        key="security_profile", name="Security profile", requires="2.10.1.0",
        entity_category=DIAGNOSTIC, entity_registry_enabled_default=False,
        value_fn=lambda d: d.get("2.10.1.0"),
    ),
    # --- conference / call ---
    PolySensorDescription(
        key="active_conferences", name="Active conferences", state_class=MEASUREMENT,
        icon="mdi:account-group", value_fn=lambda d: d.get("5.1.0"),
    ),
    PolySensorDescription(
        key="active_calls", name="Active calls", state_class=MEASUREMENT,
        icon="mdi:phone-in-talk", value_fn=lambda d: len(d.call_indexes),
    ),
    _call_text("far_site_name", "Far site name", 58, icon="mdi:account-voice"),
    _call_text("far_site_system", "Far site system", 59, icon="mdi:devices"),
    _call_num("latency", "Call latency", 18, MS, icon="mdi:timer-outline"),
    _call_num("jitter_rx", "Call jitter receive", 20, MS, icon="mdi:sine-wave"),
    _call_num("jitter_tx", "Call jitter transmit", 21, MS, icon="mdi:sine-wave"),
    _call_num("packets_lost_rx", "Packets lost receive", 14, state_class=TOTAL,
              icon="mdi:package-variant-remove"),
    _call_num("packets_lost_tx", "Packets lost transmit", 15, state_class=TOTAL,
              icon="mdi:package-variant-remove"),
    _call_num("packet_loss_rx", "Packet loss receive", 16, PERCENTAGE),
    _call_num("packet_loss_tx", "Packet loss transmit", 17, PERCENTAGE),
    _call_num("video_rate", "Video rate negotiated", 55, KBPS, RATE, enabled=False),
    _call_num("video_rate_used_rx", "Video rate receive", 56, KBPS, RATE),
    _call_num("video_rate_used_tx", "Video rate transmit", 57, KBPS, RATE),
    _call_text("video_resolution_rx", "Video resolution receive", 42, icon="mdi:video-box"),
    _call_text("video_resolution_tx", "Video resolution transmit", 43, icon="mdi:video-box"),
    PolySensorDescription(
        key="video_frame_rate_tx", name="Video frame rate transmit", state_class=MEASUREMENT,
        native_unit_of_measurement="fps", value_fn=_call_fps(45),
    ),
    _call_text("video_protocol", "Video protocol", 53, enabled=False),
    _call_text("audio_protocol", "Audio protocol", 11, enabled=False),
    _call_num("voice_jitter_rx", "Voice jitter receive", 4, MS, enabled=False),
    _call_num("voice_jitter_tx", "Voice jitter transmit", 5, MS, enabled=False),
    _call_num("video_jitter_rx", "Video jitter receive", 46, MS, enabled=False),
    _call_num("video_jitter_tx", "Video jitter transmit", 47, MS, enabled=False),
    _call_num("content_rate_used_rx", "Content rate receive", 36, KBPS, RATE, enabled=False),
    _call_num("content_rate_used_tx", "Content rate transmit", 37, KBPS, RATE, enabled=False),
    _call_text("content_resolution_rx", "Content resolution receive", 22, enabled=False),
    _call_text("content_resolution_tx", "Content resolution transmit", 23, enabled=False),
)


async def async_setup_entry(
    hass: HomeAssistant, entry: PolyConfigEntry, async_add_entities: AddEntitiesCallback
) -> None:
    coordinator = entry.runtime_data
    oids = coordinator.data.oids
    async_add_entities(
        PolySensor(coordinator, d)
        for d in DESCRIPTIONS
        if d.requires is None or d.requires in oids
    )


class PolySensor(PolyEntity, SensorEntity):
    entity_description: PolySensorDescription

    def __init__(self, coordinator, description: PolySensorDescription) -> None:
        super().__init__(coordinator, description.key)
        self.entity_description = description

    @property
    def native_value(self) -> Any:
        return self.entity_description.value_fn(self.coordinator.data)
