"""Climate platform for Tado X — one thermostat per room."""

from __future__ import annotations

from typing import Any

from homeassistant.components.climate import (
    ClimateEntity,
    ClimateEntityFeature,
    HVACAction,
    HVACMode,
)
from homeassistant.const import ATTR_TEMPERATURE, UnitOfTemperature
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from . import TadoXConfigEntry
from .entity import TadoXRoomEntity

MIN_TEMP = 5.0
MAX_TEMP = 25.0
DEFAULT_HEAT_TEMP = 20.0


async def async_setup_entry(
    hass: HomeAssistant,
    entry: TadoXConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up a climate entity for each room."""
    coordinator = entry.runtime_data
    async_add_entities(
        TadoXClimate(coordinator, room_id) for room_id in coordinator.data["rooms"]
    )


class TadoXClimate(TadoXRoomEntity, ClimateEntity):
    """A tado X room thermostat."""

    _attr_name = None
    _attr_temperature_unit = UnitOfTemperature.CELSIUS
    _attr_hvac_modes = [HVACMode.OFF, HVACMode.HEAT, HVACMode.AUTO]
    _attr_supported_features = (
        ClimateEntityFeature.TARGET_TEMPERATURE
        | ClimateEntityFeature.TURN_ON
        | ClimateEntityFeature.TURN_OFF
    )
    _attr_target_temperature_step = 0.5
    _attr_min_temp = MIN_TEMP
    _attr_max_temp = MAX_TEMP
    # New integration: opt out of the legacy turn-on/off compatibility shim.
    _enable_turn_on_off_backwards_compatibility = False

    def __init__(self, coordinator, room_id: int) -> None:
        super().__init__(coordinator, room_id)
        self._attr_unique_id = f"{coordinator.home_id}_room_{room_id}_climate"

    @property
    def current_temperature(self) -> float | None:
        return (
            self.room.get("sensorDataPoints", {})
            .get("insideTemperature", {})
            .get("value")
        )

    @property
    def target_temperature(self) -> float | None:
        return (self.room.get("setting", {}).get("temperature") or {}).get("value")

    @property
    def hvac_mode(self) -> HVACMode:
        # No manual override set => following the smart schedule.
        if self.room.get("manualControlTermination") is None:
            return HVACMode.AUTO
        if self.room.get("setting", {}).get("power") == "OFF":
            return HVACMode.OFF
        return HVACMode.HEAT

    @property
    def hvac_action(self) -> HVACAction:
        if self.room.get("setting", {}).get("power") == "OFF":
            return HVACAction.OFF
        if (self.room.get("heatingPower", {}).get("percentage") or 0) > 0:
            return HVACAction.HEATING
        return HVACAction.IDLE

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        attrs: dict[str, Any] = {}
        heating = self.room.get("heatingPower", {}).get("percentage")
        if heating is not None:
            attrs["heating_power_percent"] = heating
        term = self.room.get("manualControlTermination")
        if term:
            attrs["override_type"] = term.get("type")
            if term.get("projectedExpiry"):
                attrs["override_expires"] = term.get("projectedExpiry")
        nxt = self.room.get("nextScheduleChange")
        if nxt:
            attrs["next_schedule_change"] = nxt.get("start")
            attrs["next_schedule_temperature"] = (
                nxt.get("setting", {}).get("temperature") or {}
            ).get("value")
        return attrs

    async def async_set_temperature(self, **kwargs: Any) -> None:
        temperature = kwargs.get(ATTR_TEMPERATURE)
        if temperature is None:
            return
        await self.coordinator.client.async_set_overlay(
            self.coordinator.home_id,
            self._room_id,
            power="ON",
            temperature=temperature,
        )
        await self.coordinator.async_request_refresh()

    async def async_set_hvac_mode(self, hvac_mode: HVACMode) -> None:
        client = self.coordinator.client
        home_id = self.coordinator.home_id
        if hvac_mode == HVACMode.AUTO:
            await client.async_resume_schedule(home_id, self._room_id)
        elif hvac_mode == HVACMode.OFF:
            await client.async_set_overlay(home_id, self._room_id, power="OFF")
        else:  # HEAT
            temperature = self.target_temperature or DEFAULT_HEAT_TEMP
            await client.async_set_overlay(
                home_id, self._room_id, power="ON", temperature=temperature
            )
        await self.coordinator.async_request_refresh()

    async def async_turn_on(self) -> None:
        await self.async_set_hvac_mode(HVACMode.HEAT)

    async def async_turn_off(self) -> None:
        await self.async_set_hvac_mode(HVACMode.OFF)
