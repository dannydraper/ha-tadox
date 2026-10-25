"""Async client for the tado° X cloud API.

Deliberately free of any Home Assistant imports so it can be exercised with a
plain ``aiohttp`` session in a test harness. It handles the OAuth2 device-code
login, silent token refresh (persisting the rotated refresh token via a
caller-supplied saver), and the handful of hops.tado.com endpoints the tado X
hardware actually uses.
"""

from __future__ import annotations

import asyncio
import json
import logging
import time
from collections.abc import Awaitable, Callable
from typing import Any

import aiohttp

from .const import (
    CLIENT_ID,
    DEVICE_AUTH_URL,
    HOPS_API,
    ME_URL,
    MY_API,
    SCOPE,
    TOKEN_URL,
)

_LOGGER = logging.getLogger(__name__)

# Refresh the access token this many seconds before it actually expires.
_EXPIRY_MARGIN = 30


class TadoXError(Exception):
    """A tado API call failed."""


class TadoXAuthError(TadoXError):
    """Authentication/refresh failed — the user must log in again."""


class TadoXRateLimitError(TadoXError):
    """The daily request quota has been exhausted."""


class DeviceAuthPending(Exception):
    """The user has not yet approved the device login."""


class DeviceAuthExpired(Exception):
    """The device code expired before the user approved it."""


def parse_rate_remaining(header: str | None) -> int | None:
    """Pull the remaining-requests count out of tado's ``ratelimit`` header.

    The header looks like ``"perday";r=953`` (optionally comma-separated
    policies). Returns the integer after ``r=`` for the per-day policy, or None.
    """
    if not header:
        return None
    for part in header.split(","):
        if "r=" in part:
            try:
                return int(part.split("r=", 1)[1].split(";", 1)[0].strip())
            except (ValueError, IndexError):
                return None
    return None


# --------------------------------------------------------------------------- #
# Device-code login (used by the config flow).
# --------------------------------------------------------------------------- #
async def async_start_device_auth(session: aiohttp.ClientSession) -> dict[str, Any]:
    """Begin the device-code flow; returns the verification URL, code, etc."""
    async with session.post(
        DEVICE_AUTH_URL, data={"client_id": CLIENT_ID, "scope": SCOPE}
    ) as resp:
        if resp.status != 200:
            raise TadoXAuthError(f"device_authorize failed: HTTP {resp.status}")
        return await resp.json()


async def async_poll_token(
    session: aiohttp.ClientSession, device_code: str
) -> dict[str, Any]:
    """Exchange an approved device code for tokens.

    Raises :class:`DeviceAuthPending` while the user hasn't approved yet, and
    :class:`DeviceAuthExpired` once the code is no longer valid.
    """
    async with session.post(
        TOKEN_URL,
        data={
            "client_id": CLIENT_ID,
            "device_code": device_code,
            "grant_type": "urn:ietf:params:oauth:grant-type:device_code",
        },
    ) as resp:
        body = await resp.json()
        if resp.status == 200:
            return _stamp_expiry(body)
        error = (body or {}).get("error")
        if error == "authorization_pending":
            raise DeviceAuthPending
        if error in ("expired_token", "access_denied"):
            raise DeviceAuthExpired
        if error == "slow_down":
            raise DeviceAuthPending  # caller will back off
        raise TadoXAuthError(f"token exchange failed: {body}")


def _stamp_expiry(tokens: dict[str, Any]) -> dict[str, Any]:
    """Add an absolute ``expires_at`` so refresh timing survives restarts."""
    tokens = dict(tokens)
    tokens["expires_at"] = time.time() + tokens.get("expires_in", 600)
    return tokens


# --------------------------------------------------------------------------- #
# Authenticated client.
# --------------------------------------------------------------------------- #
class TadoXClient:
    """Minimal authenticated client for the tado X endpoints."""

    def __init__(
        self,
        session: aiohttp.ClientSession,
        tokens: dict[str, Any],
        token_saver: Callable[[dict[str, Any]], Awaitable[None]] | None = None,
    ) -> None:
        self._session = session
        self._tokens = dict(tokens)
        self._token_saver = token_saver
        self._refresh_lock = asyncio.Lock()
        self.rate_remaining: int | None = None

    @property
    def tokens(self) -> dict[str, Any]:
        """The current token set (so callers can persist it)."""
        return dict(self._tokens)

    async def _ensure_fresh_token(self) -> None:
        if time.time() > self._tokens.get("expires_at", 0) - _EXPIRY_MARGIN:
            await self._refresh()

    async def _refresh(self) -> None:
        async with self._refresh_lock:
            # Another coroutine may have refreshed while we waited for the lock.
            if time.time() <= self._tokens.get("expires_at", 0) - _EXPIRY_MARGIN:
                return
            async with self._session.post(
                TOKEN_URL,
                data={
                    "client_id": CLIENT_ID,
                    "grant_type": "refresh_token",
                    "refresh_token": self._tokens["refresh_token"],
                },
            ) as resp:
                if resp.status != 200:
                    raise TadoXAuthError(f"refresh failed: HTTP {resp.status}")
                self._tokens = _stamp_expiry(await resp.json())
            # Persist the ROTATED refresh token — the fix for daily re-auth.
            if self._token_saver:
                await self._token_saver(self.tokens)

    async def _request(
        self, method: str, url: str, json_body: Any = None, _retry: bool = True
    ) -> Any:
        await self._ensure_fresh_token()
        headers = {"Authorization": f"Bearer {self._tokens['access_token']}"}
        async with self._session.request(
            method, url, json=json_body, headers=headers
        ) as resp:
            remaining = parse_rate_remaining(resp.headers.get("ratelimit"))
            if remaining is not None:
                self.rate_remaining = remaining
            if resp.status == 401 and _retry:
                await self._refresh()
                return await self._request(method, url, json_body, _retry=False)
            if resp.status == 429:
                raise TadoXRateLimitError("daily tado API limit reached")
            if resp.status >= 400:
                raise TadoXError(
                    f"{method} {url} -> HTTP {resp.status}: {(await resp.text())[:200]}"
                )
            text = await resp.text()
            return json.loads(text) if text.strip() else {}

    # -- Reads ------------------------------------------------------------- #
    async def async_get_me(self) -> dict[str, Any]:
        return await self._request("GET", ME_URL)

    async def async_get_rooms(self, home_id: int) -> list[dict[str, Any]]:
        return await self._request("GET", f"{HOPS_API}/homes/{home_id}/rooms")

    async def async_get_rooms_and_devices(self, home_id: int) -> dict[str, Any]:
        return await self._request(
            "GET", f"{HOPS_API}/homes/{home_id}/roomsAndDevices"
        )

    async def async_get_weather(self, home_id: int) -> dict[str, Any]:
        return await self._request("GET", f"{MY_API}/homes/{home_id}/weather")

    # -- Writes ------------------------------------------------------------ #
    async def async_set_overlay(
        self,
        home_id: int,
        room_id: int,
        *,
        power: str = "ON",
        temperature: float | None = None,
        termination: dict[str, Any] | None = None,
    ) -> None:
        """Set a manual override on a room.

        ``termination`` defaults to ``{"type": "MANUAL"}`` (hold until changed).
        For a timed override pass ``{"type": "TIMER", "durationInSeconds": N}``;
        for "until the next schedule block" pass ``{"type": "NEXT_TIME_BLOCK"}``.
        tado rejects power=ON with a null temperature, so we guard it.
        """
        setting: dict[str, Any] = {"power": power}
        if power == "ON":
            if temperature is None:
                raise TadoXError("temperature is required when power is ON")
            setting["temperature"] = {"value": temperature}
        body = {"setting": setting, "termination": termination or {"type": "MANUAL"}}
        await self._request(
            "POST", f"{HOPS_API}/homes/{home_id}/rooms/{room_id}/manualControl", body
        )

    async def async_resume_schedule(self, home_id: int, room_id: int) -> None:
        """Clear any override and follow the smart schedule again."""
        await self._request(
            "POST", f"{HOPS_API}/homes/{home_id}/rooms/{room_id}/resumeSchedule"
        )
