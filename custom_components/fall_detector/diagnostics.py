"""Diagnostics support for Fall Detector."""
# SPDX-License-Identifier: Apache-2.0

from __future__ import annotations

from typing import Any

from homeassistant.components.diagnostics import async_redact_data
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant

from .const import DOMAIN
from .coordinator import FallDetectorCoordinator

TO_REDACT = {
    "mqtt_password",
    "mqtt_username",
    "webhook_shared_secret",
    "addon_url",
    "frigate_url",
}

TO_REDACT_CONFIG = {
    "mqtt_password",
    "mqtt_username",
}


async def async_get_config_entry_diagnostics(
    hass: HomeAssistant, entry: ConfigEntry,
) -> dict[str, Any]:
    """Return diagnostics for a config entry."""
    coordinator: FallDetectorCoordinator = hass.data[DOMAIN][entry.entry_id]

    # Get status from add-on
    try:
        status = await coordinator.api.async_get_status()
    except Exception as err:
        status = {"error": str(err)}

    # Get recent events
    try:
        events = await coordinator.api.async_get_recent_events()
    except Exception:
        events = []

    # Redact sensitive data from events
    redacted_events = []
    for event in events[:10]:  # Limit to last 10
        redacted_events.append(async_redact_data(event, TO_REDACT))

    return {
        "config_entry": {
            "data": async_redact_data(dict(entry.data), TO_REDACT),
            "options": async_redact_data(dict(entry.options), TO_REDACT),
        },
        "system_status": async_redact_data(status, TO_REDACT),
        "recent_events": redacted_events,
        "coordinator": {
            "last_update_success": coordinator.last_update_success,
            "update_interval": str(coordinator.update_interval),
        },
    }
