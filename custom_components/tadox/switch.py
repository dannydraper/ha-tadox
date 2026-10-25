"""Switch platform for Tado X — enable/disable the weather cutoff."""

from __future__ import annotations

from typing import Any

from homeassistant.components.switch import SwitchEntity
from homeassistant.const import EntityCategory
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from . import TadoXConfigEntry
from .entity import TadoXHomeEntity


async def async_setup_entry(
    hass: HomeAssistant,
    entry: TadoXConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    async_add_entities([TadoXWeatherCutoffSwitch(entry.runtime_data)])


class TadoXWeatherCutoffSwitch(TadoXHomeEntity, SwitchEntity):
    """When on, heating is suppressed while it's mild enough outside.

    Only rooms following the schedule are affected; an explicit manual or timed
    override always wins.
    """

    _attr_entity_category = EntityCategory.CONFIG
    _attr_icon = "mdi:weather-sunny"
    _attr_translation_key = "weather_cutoff"

    def __init__(self, coordinator) -> None:
        super().__init__(coordinator)
        self._attr_unique_id = f"{coordinator.home_id}_weather_cutoff"

    @property
    def is_on(self) -> bool:
        return self.coordinator.cutoff_enabled

    async def async_turn_on(self, **kwargs: Any) -> None:
        await self.coordinator.async_set_cutoff_enabled(True)
        self.async_write_ha_state()

    async def async_turn_off(self, **kwargs: Any) -> None:
        await self.coordinator.async_set_cutoff_enabled(False)
        self.async_write_ha_state()
