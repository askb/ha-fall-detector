"""The Fall Detector integration."""
# SPDX-License-Identifier: Apache-2.0

from __future__ import annotations

import logging

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, ServiceCall
from homeassistant.helpers import config_validation as cv
import voluptuous as vol

from .const import (
    ATTR_CAMERA,
    DOMAIN,
    EVENT_ALERT_ACKNOWLEDGED,
    EVENT_FALL_DETECTED,
    EVENT_PERSON_RECOVERED,
    PLATFORMS,
    SERVICE_ACKNOWLEDGE_ALERT,
    SERVICE_MUTE_NOTIFICATIONS,
    SERVICE_RESET_CAMERA_STATE,
    SERVICE_TEST_ALERT,
    SERVICE_TRIGGER_REANALYSIS,
    SERVICE_UNMUTE_NOTIFICATIONS,
)
from .coordinator import FallDetectorCoordinator

_LOGGER = logging.getLogger(__name__)

SERVICE_CAMERA_SCHEMA = vol.Schema(
    {vol.Required(ATTR_CAMERA): cv.string}
)

SERVICE_OPTIONAL_CAMERA_SCHEMA = vol.Schema(
    {vol.Optional(ATTR_CAMERA): cv.string}
)


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up Fall Detector from a config entry."""
    coordinator = FallDetectorCoordinator(hass, entry)
    await coordinator.async_config_entry_first_refresh()

    hass.data.setdefault(DOMAIN, {})
    hass.data[DOMAIN][entry.entry_id] = coordinator

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)

    # Register services
    await _async_register_services(hass)

    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload a Fall Detector config entry."""
    unload_ok = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    if unload_ok:
        coordinator: FallDetectorCoordinator = hass.data[DOMAIN].pop(entry.entry_id)
        await coordinator.async_shutdown()

    # Remove services if no more entries
    if not hass.data[DOMAIN]:
        for service in [
            SERVICE_TEST_ALERT,
            SERVICE_ACKNOWLEDGE_ALERT,
            SERVICE_MUTE_NOTIFICATIONS,
            SERVICE_UNMUTE_NOTIFICATIONS,
            SERVICE_RESET_CAMERA_STATE,
            SERVICE_TRIGGER_REANALYSIS,
        ]:
            hass.services.async_remove(DOMAIN, service)

    return unload_ok


async def _async_register_services(hass: HomeAssistant) -> None:
    """Register Fall Detector services."""

    async def _get_coordinator() -> FallDetectorCoordinator | None:
        """Get the first available coordinator."""
        for entry_data in hass.data.get(DOMAIN, {}).values():
            if isinstance(entry_data, FallDetectorCoordinator):
                return entry_data
        return None

    async def handle_test_alert(call: ServiceCall) -> None:
        """Handle test_alert service call."""
        coordinator = await _get_coordinator()
        if coordinator:
            camera = call.data.get(ATTR_CAMERA, "test")
            await coordinator.api.async_test_alert(camera)
            await coordinator.async_request_refresh()

    async def handle_acknowledge_alert(call: ServiceCall) -> None:
        """Handle acknowledge_alert service call."""
        coordinator = await _get_coordinator()
        if coordinator:
            camera = call.data.get(ATTR_CAMERA)
            await coordinator.api.async_acknowledge_alert(camera)
            hass.bus.async_fire(EVENT_ALERT_ACKNOWLEDGED, {ATTR_CAMERA: camera})
            await coordinator.async_request_refresh()

    async def handle_mute(call: ServiceCall) -> None:
        """Handle mute_notifications service call."""
        coordinator = await _get_coordinator()
        if coordinator:
            await coordinator.api.async_mute_notifications()
            await coordinator.async_request_refresh()

    async def handle_unmute(call: ServiceCall) -> None:
        """Handle unmute_notifications service call."""
        coordinator = await _get_coordinator()
        if coordinator:
            await coordinator.api.async_unmute_notifications()
            await coordinator.async_request_refresh()

    async def handle_reset_camera(call: ServiceCall) -> None:
        """Handle reset_camera_state service call."""
        coordinator = await _get_coordinator()
        if coordinator:
            camera = call.data[ATTR_CAMERA]
            await coordinator.api.async_reset_camera(camera)
            await coordinator.async_request_refresh()

    async def handle_reanalysis(call: ServiceCall) -> None:
        """Handle trigger_reanalysis service call."""
        coordinator = await _get_coordinator()
        if coordinator:
            await coordinator.async_request_refresh()

    hass.services.async_register(
        DOMAIN,
        SERVICE_TEST_ALERT,
        handle_test_alert,
        schema=SERVICE_CAMERA_SCHEMA,
    )
    hass.services.async_register(
        DOMAIN,
        SERVICE_ACKNOWLEDGE_ALERT,
        handle_acknowledge_alert,
        schema=SERVICE_OPTIONAL_CAMERA_SCHEMA,
    )
    hass.services.async_register(
        DOMAIN,
        SERVICE_MUTE_NOTIFICATIONS,
        handle_mute,
    )
    hass.services.async_register(
        DOMAIN,
        SERVICE_UNMUTE_NOTIFICATIONS,
        handle_unmute,
    )
    hass.services.async_register(
        DOMAIN,
        SERVICE_RESET_CAMERA_STATE,
        handle_reset_camera,
        schema=SERVICE_CAMERA_SCHEMA,
    )
    hass.services.async_register(
        DOMAIN,
        SERVICE_TRIGGER_REANALYSIS,
        handle_reanalysis,
    )
