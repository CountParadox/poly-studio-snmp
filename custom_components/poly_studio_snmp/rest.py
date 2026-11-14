"""Async client for the Poly VideoOS REST API (optional; needs the admin login).

Endpoints follow the "Poly VideoOS REST API Reference Guide". The session cookie
returned by POST /rest/session is kept in the aiohttp cookie jar.
"""
from __future__ import annotations

import asyncio
import logging
from typing import Any

import aiohttp

_LOGGER = logging.getLogger(__name__)
_TIMEOUT = aiohttp.ClientTimeout(total=10)


class PolyRestError(Exception):
    """REST request failed."""


class PolyRestAuthError(PolyRestError):
    """Login was rejected."""


class PolyRest:
    def __init__(self, session: aiohttp.ClientSession, host: str, user: str, password: str) -> None:
        self._session = session
        self._base = f"https://{host}/rest"
        self._user = user
        self._password = password
        self._logged_in = False
        # Set after a rejected login so a wrong password is not retried every poll
        # (repeated failures can lock the account on the device).
        self.auth_failed = False

    async def login(self) -> None:
        try:
            async with self._session.post(
                f"{self._base}/session",
                json={"user": self._user, "password": self._password},
                timeout=_TIMEOUT,
            ) as resp:
                body = await self._body(resp)
                status = resp.status
        except (aiohttp.ClientError, asyncio.TimeoutError) as err:
            raise PolyRestError(f"login request failed: {err}") from err
        if status in (401, 403) or (isinstance(body, dict) and body.get("success") is False):
            self.auth_failed = True
            raise PolyRestAuthError("device rejected the user name or password")
        if status >= 400:
            raise PolyRestError(f"login returned HTTP {status}")
        self._logged_in = True

    @staticmethod
    async def _body(resp: aiohttp.ClientResponse) -> Any:
        try:
            return await resp.json(content_type=None)
        except (ValueError, aiohttp.ClientError):
            return await resp.text()

    async def request(self, method: str, path: str, payload: Any = None) -> Any:
        if self.auth_failed:
            raise PolyRestAuthError("login previously rejected; reconfigure the integration")
        if not self._logged_in:
            await self.login()
        for attempt in (1, 2):
            try:
                kwargs: dict[str, Any] = {"timeout": _TIMEOUT}
                if payload is not None:
                    kwargs["json"] = payload
                async with self._session.request(method, f"{self._base}{path}", **kwargs) as resp:
                    status = resp.status
                    body = await self._body(resp)
            except (aiohttp.ClientError, asyncio.TimeoutError) as err:
                raise PolyRestError(f"{method} {path} failed: {err}") from err
            if status in (401, 403) and attempt == 1:
                # Session expired: log in again once and retry.
                await self.login()
                continue
            if status >= 400:
                raise PolyRestError(f"{method} {path} returned HTTP {status}")
            return body
        raise PolyRestError(f"{method} {path} failed")

    async def _try(self, path: str) -> Any:
        try:
            return await self.request("GET", path)
        except PolyRestAuthError:
            raise
        except PolyRestError as err:
            _LOGGER.debug("%s", err)
            return None

    async def fetch(self) -> dict[str, Any]:
        """Read state. Individual endpoints that fail are returned as None."""
        audio = await self._try("/audio")
        video = await self._try("/video/local/mute")
        conferences = await self._try("/conferences")
        device_mode = await self._try("/system/mode/device")
        return {
            "audio": audio if isinstance(audio, dict) else None,
            "video_muted": video.get("result") if isinstance(video, dict) else None,
            "conferences": conferences if isinstance(conferences, list) else None,
            "device_mode": device_mode.get("result") if isinstance(device_mode, dict) else None,
        }

    # ---- controls ----
    async def set_mic_mute(self, muted: bool) -> None:
        await self.request("POST", "/audio/muted", bool(muted))

    async def set_volume(self, volume: int) -> None:
        await self.request("POST", "/audio/volume", int(volume))

    async def set_video_mute(self, muted: bool) -> None:
        await self.request("POST", "/video/local/mute", {"mute": bool(muted)})

    async def end_calls(self) -> None:
        conferences = await self.request("GET", "/conferences")
        for conf in conferences if isinstance(conferences, list) else []:
            conf_id = conf.get("id") if isinstance(conf, dict) else None
            if conf_id is not None:
                await self.request("DELETE", f"/conferences/{conf_id}")

    async def reboot(self) -> None:
        await self.request("POST", "/system/reboot", {"action": "reboot"})
