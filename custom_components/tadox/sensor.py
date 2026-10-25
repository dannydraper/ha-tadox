"""Sensor platform for Tado X."""

from __future__ import annotations

from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorStateClass,
)
from homeassistant.const import PERCENTAGE, EntityCategory, UnitOfTemperature
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from . import TadoXConfigEntry
from .entity import TadoXHomeEntity, TadoXRoomEntity


async def async_setup_entry(
    hass: HomeAssistant,
    entry: TadoXConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    coordinator = entry.runtime_data
    entities: list[SensorEntity] = []
    for room_id in coordinator.data["rooms"]:
        entities.append(TadoXHumiditySensor(coordinator, room_id))
        entities.append(TadoXHeatingPowerSensor(coordinator, room_id))
    entities.append(TadoXOutsideTemperatureSensor(coordinator))
    entities.append(TadoXApiQuotaSensor(coordinator))
    async_add_entities(entities)


class TadoXHumiditySensor(TadoXRoomEntity, SensorEntity):
    """Relative humidity measured in a room."""

    _attr_device_class = SensorDeviceClass.HUMIDITY
    _attr_native_unit_of_measurement = PERCENTAGE
    _attr_state_class = SensorStateClass.MEASUREMENT
    _attr_translation_key = "humidity"

    def __init__(self, coordinator, room_id: int) -> None:
        super().__init__(coordinator, room_id)
        self._attr_unique_id = f"{coordinator.home_id}_room_{room_id}_humidity"

    @property
    def native_value(self) -> int | None:
        return self.room.get("sensorDataPoints", {}).get("humidity", {}).get(
            "percentage"
        )


class TadoXHeatingPowerSensor(TadoXRoomEntity, SensorEntity):
    """tado's computed heating demand for the room (its own duty cycle)."""

    _attr_native_unit_of_measurement = PERCENTAGE
    _attr_state_class = SensorStateClass.MEASUREMENT
    _attr_icon = "mdi:radiator"
    _attr_translation_key = "heating_power"

    def __init__(self, coordinator, room_id: int) -> None:
        super().__init__(coordinator, room_id)
        self._attr_unique_id = f"{coordinator.home_id}_room_{room_id}_heating_power"

    @property
    def native_value(self) -> int | None:
        return self.room.get("heatingPower", {}).get("percentage")


class TadoXOutsideTemperatureSensor(TadoXHomeEntity, SensorEntity):
    """Outside temperature reported by tado for the home's location."""

    _attr_device_class = SensorDeviceClass.TEMPERATURE
    _attr_native_unit_of_measurement = UnitOfTemperature.CELSIUS
    _attr_state_class = SensorStateClass.MEASUREMENT
    _attr_translation_key = "outside_temperature"

    def __init__(self, coordinator) -> None:
        super().__init__(coordinator)
        self._attr_unique_id = f"{coordinator.home_id}_outside_temperature"

    @property
    def native_value(self) -> float | None:
        return (
            self.coordinator.data.get("weather", {})
            .get("outsideTemperature", {})
            .get("celsius")
        )


class TadoXApiQuotaSensor(TadoXHomeEntity, SensorEntity):
    """How many tado API requests remain in today's budget."""

    _attr_state_class = SensorStateClass.MEASUREMENT
    _attr_entity_category = EntityCategory.DIAGNOSTIC
    _attr_icon = "mdi:cloud-percent"
    _attr_translation_key = "api_requests_remaining"

    def __init__(self, coordinator) -> None:
        super().__init__(coordinator)
        self._attr_unique_id = f"{coordinator.home_id}_api_requests_remaining"

    @property
    def native_value(self) -> int | None:
        return self.coordinator.data.get("rate_remaining")
