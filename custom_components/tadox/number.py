"""Number platform for Tado X — the weather-cutoff threshold."""

from __future__ import annotations

from homeassistant.components.number import (
    NumberDeviceClass,
    NumberEntity,
    NumberMode,
)
from homeassistant.const import EntityCategory, UnitOfTemperature
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from . import TadoXConfigEntry
from .const import MAX_CUTOFF_TEMP, MIN_CUTOFF_TEMP
from .entity import TadoXHomeEntity


async def async_setup_entry(
    hass: HomeAssistant,
    entry: TadoXConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    async_add_entities([TadoXWeatherCutoffNumber(entry.runtime_data)])


class TadoXWeatherCutoffNumber(TadoXHomeEntity, NumberEntity):
    """The outside temperature at or above which heating is suppressed."""

    _attr_device_class = NumberDeviceClass.TEMPERATURE
    _attr_native_unit_of_measurement = UnitOfTemperature.CELSIUS
    _attr_native_min_value = MIN_CUTOFF_TEMP
    _attr_native_max_value = MAX_CUTOFF_TEMP
    _attr_native_step = 0.5
    _attr_mode = NumberMode.BOX
    _attr_entity_category = EntityCategory.CONFIG
    _attr_icon = "mdi:thermometer-off"
    _attr_translation_key = "weather_cutoff_temperature"

    def __init__(self, coordinator) -> None:
        super().__init__(coordinator)
        self._attr_unique_id = f"{coordinator.home_id}_weather_cutoff_temperature"

    @property
    def native_value(self) -> float:
        return self.coordinator.cutoff_threshold

    async def async_set_native_value(self, value: float) -> None:
        await self.coordinator.async_set_cutoff_threshold(value)
        self.async_write_ha_state()
