"""The Tado X integration."""

from __future__ import annotations

import logging

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import Platform
from homeassistant.core import HomeAssistant
from homeassistant.helpers import aiohttp_client

from .api import TadoXClient
from .const import CONF_TOKENS, DOMAIN
from .coordinator import TadoXCoordinator

_LOGGER = logging.getLogger(__name__)

PLATFORMS = [Platform.CLIMATE, Platform.SENSOR, Platform.BINARY_SENSOR]

type TadoXConfigEntry = ConfigEntry[TadoXCoordinator]


async def async_setup_entry(hass: HomeAssistant, entry: TadoXConfigEntry) -> bool:
    """Set up Tado X from a config entry."""
    session = aiohttp_client.async_get_clientsession(hass)

    async def save_tokens(tokens: dict) -> None:
        """Persist refreshed (rotated) tokens back into the config entry."""
        hass.config_entries.async_update_entry(
            entry, data={**entry.data, CONF_TOKENS: tokens}
        )

    client = TadoXClient(session, entry.data[CONF_TOKENS], save_tokens)
    coordinator = TadoXCoordinator(hass, entry, client)
    await coordinator.async_config_entry_first_refresh()

    entry.runtime_data = coordinator
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    entry.async_on_unload(entry.add_update_listener(_async_reload_on_options))
    return True


async def _async_reload_on_options(hass: HomeAssistant, entry: TadoXConfigEntry) -> None:
    """Reload when options (e.g. scan interval) change."""
    await hass.config_entries.async_reload(entry.entry_id)


async def async_unload_entry(hass: HomeAssistant, entry: TadoXConfigEntry) -> bool:
    """Unload a config entry."""
    return await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
