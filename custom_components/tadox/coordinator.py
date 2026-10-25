"""Data update coordinator for Tado X.

A single poll feeds every entity. Room state is fetched on the main interval;
the heavier, slower-changing device and weather data are fetched only every
``SLOW_CYCLE_EVERY`` cycles to stay within tado's daily request budget.
"""

from __future__ import annotations

import logging
from datetime import timedelta
from typing import Any

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryAuthFailed
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .api import TadoXAuthError, TadoXClient, TadoXError, TadoXRateLimitError
from .const import (
    CONF_HOME_ID,
    CONF_SCAN_INTERVAL,
    DEFAULT_SCAN_INTERVAL,
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


class TadoXCoordinator(DataUpdateCoordinator[dict[str, Any]]):
    """Polls tado and caches a merged snapshot for all entities."""

    def __init__(
        self, hass: HomeAssistant, entry: ConfigEntry, client: TadoXClient
    ) -> None:
        self.client = client
        self.home_id: int = entry.data[CONF_HOME_ID]
        self._cycle = 0
        self._devices: dict[str, Any] = {"rooms": {}, "boiler": {}}
        self._weather: dict[str, Any] = {}
        interval = entry.options.get(CONF_SCAN_INTERVAL, DEFAULT_SCAN_INTERVAL)
        super().__init__(
            hass,
            _LOGGER,
            name=DOMAIN,
            update_interval=timedelta(seconds=interval),
        )

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

        return {
            "home_id": self.home_id,
            "rooms": {room["id"]: room for room in rooms},
            "devices": self._devices,
            "weather": self._weather,
            "rate_remaining": self.client.rate_remaining,
        }
