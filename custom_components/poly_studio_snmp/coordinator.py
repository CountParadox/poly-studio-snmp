"""Data coordinator and base entities for Poly Studio SNMP."""
from __future__ import annotations

import logging

import aiohttp

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_HOST, CONF_PASSWORD, CONF_PORT, CONF_USERNAME
from homeassistant.core import HomeAssistant
from homeassistant.helpers.aiohttp_client import async_create_clientsession
from homeassistant.helpers.device_registry import CONNECTION_NETWORK_MAC, DeviceInfo
from homeassistant.helpers.update_coordinator import (
    CoordinatorEntity,
    DataUpdateCoordinator,
    UpdateFailed,
)

from .const import CONF_COMMUNITY, DOMAIN, SCAN_INTERVAL
from .rest import PolyRest, PolyRestAuthError, PolyRestError
from .snmp import PolyData, SnmpError, fetch

_LOGGER = logging.getLogger(__name__)

type PolyConfigEntry = ConfigEntry[PolyCoordinator]


def create_rest(hass: HomeAssistant, host: str, user: str, password: str) -> PolyRest:
    """Build a REST client. The device uses a self-signed certificate and an IP host."""
    session = async_create_clientsession(
        hass, verify_ssl=False, cookie_jar=aiohttp.CookieJar(unsafe=True)
    )
    return PolyRest(session, host, user, password)


class PolyCoordinator(DataUpdateCoordinator[PolyData]):
    """Polls the Poly endpoint MIB over SNMP and, if a login is configured, the REST API."""

    config_entry: PolyConfigEntry

    def __init__(self, hass: HomeAssistant, entry: PolyConfigEntry) -> None:
        super().__init__(
            hass,
            _LOGGER,
            config_entry=entry,
            name=f"{DOMAIN} {entry.data[CONF_HOST]}",
            update_interval=SCAN_INTERVAL,
        )
        self.rest: PolyRest | None = None
        if entry.data.get(CONF_PASSWORD):
            self.rest = create_rest(
                hass, entry.data[CONF_HOST], entry.data.get(CONF_USERNAME) or "admin",
                entry.data[CONF_PASSWORD],
            )
        self._rest_warned = False

    async def _async_update_data(self) -> PolyData:
        conf = self.config_entry.data
        try:
            data = await self.hass.async_add_executor_job(
                fetch, conf[CONF_HOST], conf[CONF_PORT], conf[CONF_COMMUNITY]
            )
        except SnmpError as err:
            raise UpdateFailed(str(err)) from err

        if self.rest is not None and not self.rest.auth_failed:
            try:
                data.rest = await self.rest.fetch()
                self._rest_warned = False
            except PolyRestAuthError as err:
                _LOGGER.error(
                    "REST login to %s failed (%s). REST entities are unavailable until the "
                    "integration is reconfigured with the correct login", conf[CONF_HOST], err,
                )
            except PolyRestError as err:
                if not self._rest_warned:
                    _LOGGER.warning("REST API on %s unavailable: %s", conf[CONF_HOST], err)
                    self._rest_warned = True
        return data


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


class PolyRestEntity(PolyEntity):
    """Entity backed by the REST API; unavailable when REST data is missing."""

    @property
    def rest_data(self) -> dict:
        return self.coordinator.data.rest or {}

    @property
    def available(self) -> bool:
        return super().available and self.coordinator.data.rest is not None
