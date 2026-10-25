"""Data update coordinator for Tado X.

A single poll feeds every entity. Room state is fetched on the main interval;
the heavier, slower-changing device and weather data are fetched only every
``SLOW_CYCLE_EVERY`` cycles to stay within tado's daily request budget.
"""

from __future__ import annotations

import logging
from collections.abc import Iterable
from datetime import timedelta
from typing import Any

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryAuthFailed
from homeassistant.helpers.storage import Store
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .api import TadoXAuthError, TadoXClient, TadoXError, TadoXRateLimitError
from .const import (
    CONF_HOME_ID,
    CONF_SCAN_INTERVAL,
    DEFAULT_SCAN_INTERVAL,
    DEFAULT_WEATHER_CUTOFF_TEMP,
    DOMAIN,
    SLOW_CYCLE_EVERY,
)

_LOGGER = logging.getLogger(__name__)


def _index_devices(rooms_and_devices: dict[str, Any]) -> dict[str, Any]:
    """Reshape /roomsAndDevices into {room_id: device} plus the boiler device."""
    rooms: dict[int, dict[str, Any]] = {}
    for room in rooms_and_devices.get("rooms", []):
        devices = room.get("devices", [])
        rooms[room.get("roomId")] = devices[0] if devices else {}
    others = rooms_and_devices.get("otherDevices", [])
    return {"rooms": rooms, "boiler": others[0] if others else {}}


def plan_weather_cutoff(
    rooms: list[dict[str, Any]],
    managed: Iterable[int],
    *,
    enabled: bool,
    threshold: float,
    outside_temp: float | None,
) -> tuple[set[int], set[int], set[int]]:
    """Decide the weather-cutoff actions for this cycle.

    Pure and synchronous so it can be unit-tested without Home Assistant or the
    tado API. Returns three room-id sets:

    - ``suppress``: schedule-driven rooms that would heat and should be turned
      off because it's mild enough outside.
    - ``resume``: rooms we previously suppressed that should resume the schedule
      (the warm spell is over, or the cutoff was switched off).
    - ``forget``: rooms we were managing that the user has manually taken back
      over (a manual boost always wins), so we stop tracking them.

    Only rooms *following the schedule* (``manualControlTermination is None``)
    are ever suppressed, so an explicit override is never clobbered. When the
    outside temperature is unknown, managed rooms are held as-is.
    """
    managed = set(managed)
    suppress: set[int] = set()
    resume: set[int] = set()
    forget: set[int] = set()

    cooled = outside_temp is not None and outside_temp < threshold
    active = enabled and outside_temp is not None and outside_temp >= threshold
    by_id = {room["id"]: room for room in rooms}

    for room_id in managed:
        room = by_id.get(room_id)
        power_on = (
            room is not None and (room.get("setting") or {}).get("power") == "ON"
        )
        if not enabled or cooled:
            resume.add(room_id)
        elif power_on:
            forget.add(room_id)

    if active:
        for room in rooms:
            room_id = room["id"]
            if room_id in managed or room_id in resume or room_id in forget:
                continue
            if room.get("manualControlTermination") is None and (
                room.get("setting") or {}
            ).get("power") == "ON":
                suppress.add(room_id)

    return suppress, resume, forget


class TadoXCoordinator(DataUpdateCoordinator[dict[str, Any]]):
    """Polls tado and caches a merged snapshot for all entities."""

    def __init__(
        self,
        hass: HomeAssistant,
        entry: ConfigEntry,
        client: TadoXClient,
        store: Store,
        persisted: dict[str, Any] | None = None,
    ) -> None:
        self.client = client
        self.home_id: int = entry.data[CONF_HOME_ID]
        self._cycle = 0
        self._devices: dict[str, Any] = {"rooms": {}, "boiler": {}}
        self._weather: dict[str, Any] = {}

        # Weather-cutoff state, restored from the Store so it survives restarts.
        persisted = persisted or {}
        self._store = store
        self.cutoff_enabled: bool = persisted.get("cutoff_enabled", False)
        self.cutoff_threshold: float = persisted.get(
            "cutoff_threshold", DEFAULT_WEATHER_CUTOFF_TEMP
        )
        self._cutoff_rooms: set[int] = set(persisted.get("cutoff_rooms", []))

        interval = entry.options.get(CONF_SCAN_INTERVAL, DEFAULT_SCAN_INTERVAL)
        super().__init__(
            hass,
            _LOGGER,
            name=DOMAIN,
            update_interval=timedelta(seconds=interval),
        )

    # -- Weather cutoff ---------------------------------------------------- #
    @property
    def outside_temperature(self) -> float | None:
        return (self._weather.get("outsideTemperature") or {}).get("celsius")

    @property
    def cutoff_active(self) -> bool:
        """True when the cutoff is enabled and it's currently mild enough out."""
        temp = self.outside_temperature
        return (
            self.cutoff_enabled
            and temp is not None
            and temp >= self.cutoff_threshold
        )

    async def _async_save_cutoff(self) -> None:
        await self._store.async_save(
            {
                "cutoff_enabled": self.cutoff_enabled,
                "cutoff_threshold": self.cutoff_threshold,
                "cutoff_rooms": sorted(self._cutoff_rooms),
            }
        )

    async def async_set_cutoff_enabled(self, enabled: bool) -> None:
        self.cutoff_enabled = enabled
        await self._async_save_cutoff()
        await self.async_request_refresh()  # apply immediately

    async def async_set_cutoff_threshold(self, temperature: float) -> None:
        self.cutoff_threshold = temperature
        await self._async_save_cutoff()
        await self.async_request_refresh()

    async def _async_apply_weather_cutoff(self, rooms: list[dict[str, Any]]) -> None:
        """Turn schedule-driven rooms off while mild, and restore them after."""
        suppress, resume, forget = plan_weather_cutoff(
            rooms,
            self._cutoff_rooms,
            enabled=self.cutoff_enabled,
            threshold=self.cutoff_threshold,
            outside_temp=self.outside_temperature,
        )
        if not (suppress or resume or forget):
            return
        for room_id in resume:
            try:
                await self.client.async_resume_schedule(self.home_id, room_id)
                self._cutoff_rooms.discard(room_id)
            except TadoXError as err:
                _LOGGER.warning("Weather cutoff: resume of room %s failed: %s", room_id, err)
        self._cutoff_rooms -= forget
        for room_id in suppress:
            try:
                await self.client.async_set_overlay(self.home_id, room_id, power="OFF")
                self._cutoff_rooms.add(room_id)
            except TadoXError as err:
                _LOGGER.warning("Weather cutoff: turn-off of room %s failed: %s", room_id, err)
        await self._async_save_cutoff()

    async def _async_update_data(self) -> dict[str, Any]:
        try:
            rooms = await self.client.async_get_rooms(self.home_id)
            if self._cycle % SLOW_CYCLE_EVERY == 0:
                rad = await self.client.async_get_rooms_and_devices(self.home_id)
                self._devices = _index_devices(rad)
                try:
                    self._weather = await self.client.async_get_weather(self.home_id)
                except TadoXError as err:
                    _LOGGER.debug("Weather fetch failed (non-fatal): %s", err)
            self._cycle += 1
        except TadoXAuthError as err:
            raise ConfigEntryAuthFailed(str(err)) from err
        except (TadoXRateLimitError, TadoXError) as err:
            raise UpdateFailed(str(err)) from err

        # Auxiliary control loop: must never take the whole poll down.
        try:
            await self._async_apply_weather_cutoff(rooms)
        except Exception:  # noqa: BLE001 - defensive; keep polling alive
            _LOGGER.exception("Weather cutoff enforcement failed")

        return {
            "home_id": self.home_id,
            "rooms": {room["id"]: room for room in rooms},
            "devices": self._devices,
            "weather": self._weather,
            "rate_remaining": self.client.rate_remaining,
        }
