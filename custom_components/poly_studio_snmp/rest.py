"""Async client for the Poly VideoOS REST API (optional; needs the admin login).

Endpoints follow the "Poly VideoOS REST API Reference Guide". The session cookie
returned by POST /rest/session is kept in the aiohttp cookie jar.
"""
from __future__ import annotations

import asyncio
import json
import logging
from typing import Any
from urllib.parse import quote

import aiohttp

_LOGGER = logging.getLogger(__name__)
_TIMEOUT = aiohttp.ClientTimeout(total=10)

SNAPSHOT_IDS = {
    "near": "near_image_1.jpg",
    "far": "far_image_1.jpg",
    "content": "content_image_1.jpg",
}


class PolyRestError(Exception):
    """REST request failed."""


class PolyRestAuthError(PolyRestError):
    """Login was rejected."""


def _as_list(value: Any) -> list[dict]:
    """The guide shows some list endpoints as a single object; accept both."""
    if isinstance(value, dict):
        value = [value]
    return [v for v in value if isinstance(v, dict)] if isinstance(value, list) else []


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
                status = resp.status
                body = self._parse(await resp.read())
        except (aiohttp.ClientError, asyncio.TimeoutError) as err:
            raise PolyRestError(f"login request failed: {err}") from err
        if status in (401, 403) or (isinstance(body, dict) and body.get("success") is False):
            self.auth_failed = True
            raise PolyRestAuthError("device rejected the user name or password")
        if status >= 400:
            raise PolyRestError(f"login returned HTTP {status}")
        self._logged_in = True

    @staticmethod
    def _parse(raw: bytes) -> Any:
        try:
            return json.loads(raw)
        except ValueError:
            return raw.decode("utf-8", errors="replace")

    async def request_raw(self, method: str, path: str, payload: Any = None,
                          params: dict[str, Any] | None = None) -> bytes:
        if self.auth_failed:
            raise PolyRestAuthError("login previously rejected; reconfigure the integration")
        if not self._logged_in:
            await self.login()
        for attempt in (1, 2):
            try:
                kwargs: dict[str, Any] = {"timeout": _TIMEOUT}
                if payload is not None:
                    kwargs["json"] = payload
                if params:
                    kwargs["params"] = params
                async with self._session.request(method, f"{self._base}{path}", **kwargs) as resp:
                    status = resp.status
                    raw = await resp.read()
            except (aiohttp.ClientError, asyncio.TimeoutError) as err:
                raise PolyRestError(f"{method} {path} failed: {err}") from err
            if status in (401, 403) and attempt == 1:
                # Session expired: log in again once and retry.
                await self.login()
                continue
            if status >= 400:
                raise PolyRestError(f"{method} {path} returned HTTP {status}")
            return raw
        raise PolyRestError(f"{method} {path} failed")

    async def request(self, method: str, path: str, payload: Any = None,
                      params: dict[str, Any] | None = None) -> Any:
        return self._parse(await self.request_raw(method, path, payload, params))

    async def _try(self, path: str) -> Any:
        try:
            return await self.request("GET", path)
        except PolyRestAuthError:
            raise
        except PolyRestError as err:
            _LOGGER.debug("%s", err)
            return None

    @staticmethod
    def _result(value: Any) -> bool | None:
        return value.get("result") if isinstance(value, dict) else None

    async def fetch(self) -> dict[str, Any]:
        """Read state. Individual endpoints that fail are returned as None / empty."""
        audio = await self._try("/audio")
        conferences = await self._try("/conferences")
        calendar = await self._try("/calendar")
        cal_status = None
        if isinstance(calendar, dict):
            cal_status = calendar.get("Status") or calendar.get("status")
        meetings: list[dict] = []
        if cal_status not in (None, "DISABLED"):
            meetings = _as_list(await self._try("/calendar/meetings"))
        return {
            "audio": audio if isinstance(audio, dict) else None,
            "video_muted": self._result(await self._try("/video/local/mute")),
            "conferences": conferences if isinstance(conferences, list) else None,
            "device_mode": self._result(await self._try("/system/mode/device")),
            "signage": self._result(await self._try("/system/mode/signage")),
            "presets": _as_list(await self._try("/cameras/near/presets/all")),
            "calendar_status": cal_status,
            "meetings": meetings,
        }

    # ---- audio / video ----
    async def set_mic_mute(self, muted: bool) -> None:
        await self.request("POST", "/audio/muted", bool(muted))

    async def set_volume(self, volume: int) -> None:
        await self.request("POST", "/audio/volume", int(volume))

    async def set_video_mute(self, muted: bool) -> None:
        await self.request("POST", "/video/local/mute", {"mute": bool(muted)})

    async def send_dtmf(self, digits: str) -> None:
        for char in digits:
            if char in "0123456789*#":
                await self.request("POST", "/audio", {"action": "playDTMF", "dtmfChar": char})
                await asyncio.sleep(0.25)
            elif char == ",":
                await asyncio.sleep(1)

    # ---- calls ----
    async def dial(self, address: str, dial_type: str = "AUTO", rate: int | None = None,
                   password: str | None = None) -> None:
        payload: dict[str, Any] = {"address": address, "dialType": dial_type}
        if rate:
            payload["rate"] = int(rate)
        if password:
            payload["password"] = password
        await self.request("POST", "/conferences", payload)

    async def answer(self) -> None:
        """Answer every answerable incoming connection.

        The reference guide documents the `answerable` flag but not the answer request
        itself; this uses the connection action form used by Poly's own clients.
        """
        answered = False
        for conf in _as_list(await self.request("GET", "/conferences")):
            for conn in _as_list(conf.get("connections")):
                if conn.get("answerable") and conf.get("id") is not None and conn.get("id") is not None:
                    await self.request(
                        "POST", f"/conferences/{conf['id']}/connections/{conn['id']}",
                        {"action": "answer"},
                    )
                    answered = True
        if not answered:
            raise PolyRestError("there is no incoming call to answer")

    async def end_calls(self) -> None:
        for conf in _as_list(await self.request("GET", "/conferences")):
            if conf.get("id") is not None:
                await self.request("DELETE", f"/conferences/{conf['id']}")

    # ---- camera ----
    async def preset(self, index: int, action: str = "activate") -> None:
        await self.request("POST", f"/cameras/near/presets/{int(index)}", {"action": action})

    async def snapshot(self, which: str = "near") -> bytes:
        return await self.request_raw("GET", f"/cameras/snapshot/{SNAPSHOT_IDS[which]}")

    # ---- modes ----
    async def set_signage(self, on: bool) -> None:
        await self.request("POST" if on else "DELETE", "/system/mode/signage")

    # ---- calendar ----
    async def meetings(self, start: int, end: int) -> list[dict]:
        return _as_list(
            await self.request("GET", "/calendar/meetings", params={"start": start, "end": end})
        )

    async def join_meeting(self, meeting_id: str) -> None:
        await self.request("POST", f"/calendar/meetings/{quote(str(meeting_id), safe='')}")

    # ---- system ----
    async def reboot(self) -> None:
        await self.request("POST", "/system/reboot", {"action": "reboot"})
