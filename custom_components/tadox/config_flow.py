"""Config and options flow for Tado X (OAuth2 device-code login)."""

from __future__ import annotations

import asyncio
import logging
import time
from typing import Any

import voluptuous as vol

from homeassistant.config_entries import (
    ConfigFlow,
    ConfigFlowResult,
    OptionsFlow,
)
from homeassistant.core import callback
from homeassistant.helpers import aiohttp_client

from . import api
from .api import DeviceAuthExpired, DeviceAuthPending, TadoXError
from .const import (
    CONF_HOME_ID,
    CONF_HOME_NAME,
    CONF_SCAN_INTERVAL,
    CONF_TOKENS,
    DEFAULT_SCAN_INTERVAL,
    DOMAIN,
    MAX_SCAN_INTERVAL,
    MIN_SCAN_INTERVAL,
)

_LOGGER = logging.getLogger(__name__)


class TadoXConfigFlow(ConfigFlow, domain=DOMAIN):
    """Handle the device-code login flow."""

    VERSION = 1

    def __init__(self) -> None:
        self._device: dict[str, Any] | None = None
        self._task: asyncio.Task[dict[str, Any]] | None = None
        self._tokens: dict[str, Any] | None = None

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Start/continue the device-code flow, showing progress while we wait."""
        session = aiohttp_client.async_get_clientsession(self.hass)

        if self._device is None:
            try:
                self._device = await api.async_start_device_auth(session)
            except TadoXError:
                return self.async_abort(reason="cannot_connect")

        if self._task is None:
            self._task = self.hass.async_create_task(self._poll_for_token(session))

        if not self._task.done():
            return self.async_show_progress(
                step_id="user",
                progress_action="wait_for_authorization",
                description_placeholders={
                    "url": self._device.get("verification_uri_complete")
                    or self._device.get("verification_uri", ""),
                    "code": self._device.get("user_code", ""),
                },
                progress_task=self._task,
            )

        try:
            self._tokens = self._task.result()
        except DeviceAuthExpired:
            return self.async_show_progress_done(next_step_id="timeout")
        except Exception:  # noqa: BLE001 - surface any failure as a clean abort
            _LOGGER.exception("Tado X device login failed")
            return self.async_show_progress_done(next_step_id="failed")

        return self.async_show_progress_done(next_step_id="finish")

    async def _poll_for_token(self, session) -> dict[str, Any]:
        """Poll tado until the user approves, or the code expires."""
        assert self._device is not None
        device_code = self._device["device_code"]
        interval = self._device.get("interval", 5)
        deadline = time.time() + self._device.get("expires_in", 300)
        while time.time() < deadline:
            try:
                return await api.async_poll_token(session, device_code)
            except DeviceAuthPending:
                await asyncio.sleep(interval)
        raise DeviceAuthExpired

    async def async_step_finish(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Look up the home and create (or update, on reauth) the entry."""
        assert self._tokens is not None
        session = aiohttp_client.async_get_clientsession(self.hass)
        client = api.TadoXClient(session, self._tokens)
        try:
            me = await client.async_get_me()
        except TadoXError:
            return self.async_abort(reason="cannot_connect")

        homes = me.get("homes", [])
        if not homes:
            return self.async_abort(reason="no_homes")
        home = homes[0]
        home_id = home["id"]

        if self.source == "reauth":
            entry = self._get_reauth_entry()
            self.hass.config_entries.async_update_entry(
                entry, data={**entry.data, CONF_TOKENS: self._tokens}
            )
            await self.hass.config_entries.async_reload(entry.entry_id)
            return self.async_abort(reason="reauth_successful")

        await self.async_set_unique_id(str(home_id))
        self._abort_if_unique_id_configured()
        return self.async_create_entry(
            title=home.get("name", "Tado X"),
            data={
                CONF_TOKENS: self._tokens,
                CONF_HOME_ID: home_id,
                CONF_HOME_NAME: home.get("name"),
            },
        )

    async def async_step_timeout(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """The device code expired before approval — let the user retry."""
        self._device = None
        self._task = None
        if user_input is not None:
            return await self.async_step_user()
        return self.async_show_form(step_id="timeout")

    async def async_step_failed(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        return self.async_abort(reason="cannot_authenticate")

    async def async_step_reauth(
        self, entry_data: dict[str, Any]
    ) -> ConfigFlowResult:
        """Triggered when tokens go bad; re-run the device login."""
        return await self.async_step_user()

    @staticmethod
    @callback
    def async_get_options_flow(config_entry) -> TadoXOptionsFlow:
        return TadoXOptionsFlow()


class TadoXOptionsFlow(OptionsFlow):
    """Let the user tune the poll interval (to manage the daily API budget)."""

    async def async_step_init(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        if user_input is not None:
            return self.async_create_entry(title="", data=user_input)

        current = self.config_entry.options.get(
            CONF_SCAN_INTERVAL, DEFAULT_SCAN_INTERVAL
        )
        schema = vol.Schema(
            {
                vol.Optional(CONF_SCAN_INTERVAL, default=current): vol.All(
                    vol.Coerce(int),
                    vol.Range(min=MIN_SCAN_INTERVAL, max=MAX_SCAN_INTERVAL),
                )
            }
        )
        return self.async_show_form(step_id="init", data_schema=schema)
