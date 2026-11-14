"""Data coordinator and base entity for Poly Studio SNMP."""
from __future__ import annotations

import logging

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_HOST, CONF_PORT
from homeassistant.core import HomeAssistant
from homeassistant.helpers.device_registry import CONNECTION_NETWORK_MAC, DeviceInfo
from homeassistant.helpers.update_coordinator import (
    CoordinatorEntity,
    DataUpdateCoordinator,
    UpdateFailed,
)

from .const import CONF_COMMUNITY, DOMAIN, SCAN_INTERVAL
from .snmp import PolyData, SnmpError, fetch

_LOGGER = logging.getLogger(__name__)

type PolyConfigEntry = ConfigEntry[PolyCoordinator]


class PolyCoordinator(DataUpdateCoordinator[PolyData]):
    """Polls the Poly endpoint MIB in one walk."""

    config_entry: PolyConfigEntry

    def __init__(self, hass: HomeAssistant, entry: PolyConfigEntry) -> None:
        super().__init__(
            hass,
            _LOGGER,
            config_entry=entry,
            name=f"{DOMAIN} {entry.data[CONF_HOST]}",
            update_interval=SCAN_INTERVAL,
        )

    async def _async_update_data(self) -> PolyData:
        data = self.config_entry.data
        try:
            return await self.hass.async_add_executor_job(
                fetch, data[CONF_HOST], data[CONF_PORT], data[CONF_COMMUNITY]
            )
        except SnmpError as err:
            raise UpdateFailed(str(err)) from err


class PolyEntity(CoordinatorEntity[PolyCoordinator]):
    """Base entity bound to the video bar device."""

    _attr_has_entity_name = True

    def __init__(self, coordinator: PolyCoordinator, key: str) -> None:
        super().__init__(coordinator)
        data = coordinator.data
        serial = data.get("1.5.0")
        self._attr_unique_id = f"{serial}_{key}"
        mac = data.get("3.10.2.1.3.1")
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, serial)},
            connections={(CONNECTION_NETWORK_MAC, mac)} if mac else set(),
            manufacturer="Poly",
            model=data.get("1.4.0"),
            name=data.sys_name or data.get("1.4.0"),
            sw_version=data.get("1.1.0"),
            serial_number=serial,
            configuration_url=f"https://{coordinator.config_entry.data[CONF_HOST]}",
        )
