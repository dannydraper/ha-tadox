"""Binary sensor platform for Tado X."""

from __future__ import annotations

from homeassistant.components.binary_sensor import (
    BinarySensorDeviceClass,
    BinarySensorEntity,
)
from homeassistant.const import EntityCategory
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from . import TadoXConfigEntry
from .entity import TadoXRoomEntity


async def async_setup_entry(
    hass: HomeAssistant,
    entry: TadoXConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    coordinator = entry.runtime_data
    entities: list[BinarySensorEntity] = []
    for room_id in coordinator.data["rooms"]:
        entities.append(TadoXWindowSensor(coordinator, room_id))
        entities.append(TadoXConnectivitySensor(coordinator, room_id))
        entities.append(TadoXBatterySensor(coordinator, room_id))
    async_add_entities(entities)


class TadoXWindowSensor(TadoXRoomEntity, BinarySensorEntity):
    """Open-window detection for a room."""

    _attr_device_class = BinarySensorDeviceClass.WINDOW
    _attr_translation_key = "window_open"

    def __init__(self, coordinator, room_id: int) -> None:
        super().__init__(coordinator, room_id)
        self._attr_unique_id = f"{coordinator.home_id}_room_{room_id}_window"

    @property
    def is_on(self) -> bool:
        return self.room.get("openWindow") is not None


class TadoXConnectivitySensor(TadoXRoomEntity, BinarySensorEntity):
    """Whether the room's device is connected."""

    _attr_device_class = BinarySensorDeviceClass.CONNECTIVITY
    _attr_entity_category = EntityCategory.DIAGNOSTIC
    _attr_translation_key = "connectivity"

    def __init__(self, coordinator, room_id: int) -> None:
        super().__init__(coordinator, room_id)
        self._attr_unique_id = f"{coordinator.home_id}_room_{room_id}_connectivity"

    # Report connectivity even when the device is offline.
    @property
    def available(self) -> bool:
        return self.coordinator.last_update_success

    @property
    def is_on(self) -> bool:
        return self.room.get("connection", {}).get("state") == "CONNECTED"


class TadoXBatterySensor(TadoXRoomEntity, BinarySensorEntity):
    """Low-battery warning for the room's device."""

    _attr_device_class = BinarySensorDeviceClass.BATTERY
    _attr_entity_category = EntityCategory.DIAGNOSTIC
    _attr_translation_key = "battery_low"

    def __init__(self, coordinator, room_id: int) -> None:
        super().__init__(coordinator, room_id)
        self._attr_unique_id = f"{coordinator.home_id}_room_{room_id}_battery"

    @property
    def is_on(self) -> bool:
        state = self._device.get("batteryState")
        return state is not None and state != "NORMAL"
