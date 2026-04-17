"""DataUpdateCoordinator for the Fall Detector integration."""
# SPDX-License-Identifier: Apache-2.0

from __future__ import annotations

import logging
from datetime import timedelta
from typing import Any

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .api import FallDetectorApi, FallDetectorApiError, FallDetectorConnectionError
from .const import CONF_ADDON_URL, DEFAULT_SCAN_INTERVAL, DOMAIN

_LOGGER = logging.getLogger(__name__)


class FallDetectorData:
    """Structured data from the Fall Detector add-on."""

    def __init__(self, raw_status: dict[str, Any]) -> None:
        """Initialize from raw API status response."""
        self.raw = raw_status
        self.online: bool = raw_status.get("online", False)
        self.version: str = raw_status.get("version", "unknown")
        self.uptime_seconds: float = raw_status.get("uptime_seconds", 0.0)
        self.cameras: dict[str, dict[str, Any]] = raw_status.get("cameras", {})
        self.active_alerts: int = raw_status.get("active_alerts", 0)
        self.total_events: int = raw_status.get("total_events", 0)
        self.last_event: dict[str, Any] | None = raw_status.get("last_event")
        self.notifications_muted: bool = raw_status.get("notifications_muted", False)

    def get_camera_state(self, camera_name: str) -> dict[str, Any] | None:
        """Get state for a specific camera."""
        return self.cameras.get(camera_name)

    def is_camera_alerting(self, camera_name: str) -> bool:
        """Check if a camera has an active alert."""
        cam = self.cameras.get(camera_name, {})
        return cam.get("active_alert", False)

    def get_camera_confidence(self, camera_name: str) -> float:
        """Get the last fall confidence for a camera."""
        cam = self.cameras.get(camera_name, {})
        last_event = cam.get("last_fall_event")
        if last_event:
            return last_event.get("confidence", 0.0)
        return 0.0

    def get_camera_last_fall_time(self, camera_name: str) -> str | None:
        """Get the timestamp of the last fall event for a camera."""
        cam = self.cameras.get(camera_name, {})
        last_event = cam.get("last_fall_event")
        if last_event:
            return last_event.get("timestamp")
        return None

    def is_camera_monitoring(self, camera_name: str) -> bool:
        """Check if a camera is actively being monitored."""
        cam = self.cameras.get(camera_name, {})
        return cam.get("monitoring_active", False)

    def is_camera_alerts_enabled(self, camera_name: str) -> bool:
        """Check if alerts are enabled for a camera."""
        cam = self.cameras.get(camera_name, {})
        return cam.get("alerts_enabled", True)


class FallDetectorCoordinator(DataUpdateCoordinator[FallDetectorData]):
    """Coordinator to manage fetching data from the Fall Detector add-on."""

    config_entry: ConfigEntry

    def __init__(self, hass: HomeAssistant, config_entry: ConfigEntry) -> None:
        """Initialize the coordinator."""
        self.api = FallDetectorApi(
            base_url=config_entry.data.get(CONF_ADDON_URL, "http://localhost:8099"),
        )
        super().__init__(
            hass,
            _LOGGER,
            name=DOMAIN,
            config_entry=config_entry,
            update_interval=timedelta(seconds=DEFAULT_SCAN_INTERVAL),
            always_update=False,
        )

    async def _async_update_data(self) -> FallDetectorData:
        """Fetch data from the add-on API."""
        try:
            status = await self.api.async_get_status()
            return FallDetectorData(status)
        except FallDetectorConnectionError as err:
            raise UpdateFailed(
                f"Cannot connect to Fall Detector add-on: {err}"
            ) from err
        except FallDetectorApiError as err:
            raise UpdateFailed(
                f"Error fetching Fall Detector data: {err}"
            ) from err

    async def async_shutdown(self) -> None:
        """Clean up on shutdown."""
        await self.api.async_close()
        await super().async_shutdown()
