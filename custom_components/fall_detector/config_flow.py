"""Config flow for Fall Detector integration."""
# SPDX-License-Identifier: Apache-2.0

from __future__ import annotations

import logging
from typing import Any

import voluptuous as vol

from homeassistant import config_entries
from homeassistant.core import callback
from homeassistant.data_entry_flow import FlowResult
from homeassistant.helpers import selector

from .api import FallDetectorApi, FallDetectorApiError, FallDetectorConnectionError
from .const import (
    CONF_ADDON_URL,
    CONF_ALERT_COOLDOWN,
    CONF_CONFIDENCE_THRESHOLD,
    CONF_DEBUG_LOGGING,
    CONF_ESCALATION_ENABLED,
    CONF_FALL_CONFIRMATION,
    CONF_FRIGATE_URL,
    CONF_MONITORED_CAMERAS,
    CONF_NOTIFICATION_TARGETS,
    CONF_QUIET_HOURS_END,
    CONF_QUIET_HOURS_START,
    CONF_RECOVERY_WINDOW,
    DEFAULT_ADDON_URL,
    DOMAIN,
)

_LOGGER = logging.getLogger(__name__)


class FallDetectorConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Handle a config flow for Fall Detector."""

    VERSION = 1

    def __init__(self) -> None:
        """Initialize the config flow."""
        self._addon_url: str = DEFAULT_ADDON_URL
        self._frigate_url: str = ""
        self._available_cameras: list[str] = []
        self._data: dict[str, Any] = {}

    async def async_step_user(
        self,
        user_input: dict[str, Any] | None = None,
    ) -> FlowResult:
        """Handle the initial step - add-on connection."""
        errors: dict[str, str] = {}

        if user_input is not None:
            self._addon_url = user_input[CONF_ADDON_URL]
            api = FallDetectorApi(base_url=self._addon_url)
            try:
                health = await api.async_get_health()
                if health.get("status") == "ok":
                    self._data[CONF_ADDON_URL] = self._addon_url
                    await api.async_close()
                    return await self.async_step_frigate()
                errors["base"] = "cannot_connect"
            except FallDetectorConnectionError:
                errors["base"] = "cannot_connect"
            except FallDetectorApiError:
                errors["base"] = "unknown"
            finally:
                await api.async_close()

        return self.async_show_form(
            step_id="user",
            data_schema=vol.Schema(
                {
                    vol.Required(CONF_ADDON_URL, default=self._addon_url): str,
                }
            ),
            errors=errors,
        )

    async def async_step_frigate(
        self,
        user_input: dict[str, Any] | None = None,
    ) -> FlowResult:
        """Handle Frigate URL configuration."""
        errors: dict[str, str] = {}

        if user_input is not None:
            self._frigate_url = user_input[CONF_FRIGATE_URL]
            self._data[CONF_FRIGATE_URL] = self._frigate_url

            # Try to discover cameras via the add-on
            api = FallDetectorApi(base_url=self._addon_url)
            try:
                status = await api.async_get_status()
                cameras = list(status.get("cameras", {}).keys())
                if cameras:
                    self._available_cameras = cameras
                    await api.async_close()
                    return await self.async_step_cameras()
            except Exception:
                _LOGGER.debug("Could not discover cameras, proceeding anyway")
            finally:
                await api.async_close()

            # If no cameras found, finish with empty list
            self._data[CONF_MONITORED_CAMERAS] = []
            return self._create_entry()

        return self.async_show_form(
            step_id="frigate",
            data_schema=vol.Schema(
                {
                    vol.Required(
                        CONF_FRIGATE_URL,
                        default="http://ccab4aaf-frigate:5000",
                    ): str,
                }
            ),
            errors=errors,
        )

    async def async_step_cameras(
        self,
        user_input: dict[str, Any] | None = None,
    ) -> FlowResult:
        """Handle camera selection."""
        if user_input is not None:
            self._data[CONF_MONITORED_CAMERAS] = user_input.get(
                CONF_MONITORED_CAMERAS, []
            )
            return self._create_entry()

        camera_options = [
            selector.SelectOptionDict(value=cam, label=cam)
            for cam in self._available_cameras
        ]

        return self.async_show_form(
            step_id="cameras",
            data_schema=vol.Schema(
                {
                    vol.Required(CONF_MONITORED_CAMERAS): selector.SelectSelector(
                        selector.SelectSelectorConfig(
                            options=camera_options,
                            multiple=True,
                            mode=selector.SelectSelectorMode.LIST,
                        )
                    ),
                }
            ),
        )

    def _create_entry(self) -> FlowResult:
        """Create the config entry."""
        return self.async_create_entry(
            title="Fall Detector",
            data=self._data,
        )

    @staticmethod
    @callback
    def async_get_options_flow(
        config_entry: config_entries.ConfigEntry,
    ) -> FallDetectorOptionsFlow:
        """Get the options flow handler."""
        return FallDetectorOptionsFlow()


class FallDetectorOptionsFlow(config_entries.OptionsFlow):
    """Handle Fall Detector options."""

    async def async_step_init(
        self,
        user_input: dict[str, Any] | None = None,
    ) -> FlowResult:
        """Manage the options."""
        if user_input is not None:
            return self.async_create_entry(data=user_input)

        current = self.config_entry.options

        return self.async_show_form(
            step_id="init",
            data_schema=vol.Schema(
                {
                    vol.Optional(
                        CONF_CONFIDENCE_THRESHOLD,
                        default=current.get(CONF_CONFIDENCE_THRESHOLD, 0.7),
                    ): selector.NumberSelector(
                        selector.NumberSelectorConfig(
                            min=0.3,
                            max=1.0,
                            step=0.05,
                            mode=selector.NumberSelectorMode.SLIDER,
                        )
                    ),
                    vol.Optional(
                        CONF_FALL_CONFIRMATION,
                        default=current.get(CONF_FALL_CONFIRMATION, 5),
                    ): selector.NumberSelector(
                        selector.NumberSelectorConfig(
                            min=1,
                            max=30,
                            step=1,
                            unit_of_measurement="seconds",
                        )
                    ),
                    vol.Optional(
                        CONF_RECOVERY_WINDOW,
                        default=current.get(CONF_RECOVERY_WINDOW, 30),
                    ): selector.NumberSelector(
                        selector.NumberSelectorConfig(
                            min=10,
                            max=120,
                            step=5,
                            unit_of_measurement="seconds",
                        )
                    ),
                    vol.Optional(
                        CONF_ALERT_COOLDOWN,
                        default=current.get(CONF_ALERT_COOLDOWN, 120),
                    ): selector.NumberSelector(
                        selector.NumberSelectorConfig(
                            min=30,
                            max=600,
                            step=10,
                            unit_of_measurement="seconds",
                        )
                    ),
                    vol.Optional(
                        CONF_ESCALATION_ENABLED,
                        default=current.get(CONF_ESCALATION_ENABLED, True),
                    ): bool,
                    vol.Optional(
                        CONF_QUIET_HOURS_START,
                        default=current.get(CONF_QUIET_HOURS_START, ""),
                    ): str,
                    vol.Optional(
                        CONF_QUIET_HOURS_END,
                        default=current.get(CONF_QUIET_HOURS_END, ""),
                    ): str,
                    vol.Optional(
                        CONF_DEBUG_LOGGING,
                        default=current.get(CONF_DEBUG_LOGGING, False),
                    ): bool,
                }
            ),
        )
