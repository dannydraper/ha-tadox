"""Shared base entities for Tado X."""

from __future__ import annotations

from typing import Any

from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN, MANUFACTURER
from .coordinator import TadoXCoordinator


class TadoXRoomEntity(CoordinatorEntity[TadoXCoordinator]):
    """Base for entities that belong to a single tado room."""

    _attr_has_entity_name = True

    def __init__(self, coordinator: TadoXCoordinator, room_id: int) -> None:
        super().__init__(coordinator)
        self._room_id = room_id

    @property
    def room(self) -> dict[str, Any]:
        return self.coordinator.data["rooms"].get(self._room_id, {})

    @property
    def _device(self) -> dict[str, Any]:
        return self.coordinator.data["devices"]["rooms"].get(self._room_id, {})

    @property
    def device_info(self) -> DeviceInfo:
        return DeviceInfo(
            identifiers={(DOMAIN, f"{self.coordinator.home_id}_room_{self._room_id}")},
            name=self.room.get("name"),
            manufacturer=MANUFACTURER,
            model=self._device.get("type"),
            sw_version=self._device.get("firmwareVersion"),
            serial_number=self._device.get("serialNumber"),
        )

    @property
    def available(self) -> bool:
        return (
            super().available
            and self.room.get("connection", {}).get("state") == "CONNECTED"
        )


class TadoXHomeEntity(CoordinatorEntity[TadoXCoordinator]):
    """Base for home-wide entities (weather, diagnostics)."""

    _attr_has_entity_name = True

    @property
    def device_info(self) -> DeviceInfo:
        boiler = self.coordinator.data["devices"].get("boiler", {})
        return DeviceInfo(
            identifiers={(DOMAIN, str(self.coordinator.home_id))},
            name="tado° System",
            manufacturer=MANUFACTURER,
            model=boiler.get("type"),
            sw_version=boiler.get("firmwareVersion"),
            serial_number=boiler.get("serialNumber"),
        )
