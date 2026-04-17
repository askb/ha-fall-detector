"""Switch platform for Fall Detector."""
# SPDX-License-Identifier: Apache-2.0

from __future__ import annotations

import logging
from typing import Any

from homeassistant.components.switch import SwitchDeviceClass, SwitchEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import CONF_MONITORED_CAMERAS, DOMAIN
from .coordinator import FallDetectorCoordinator

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up Fall Detector switches."""
    coordinator: FallDetectorCoordinator = hass.data[DOMAIN][entry.entry_id]
    cameras: list[str] = entry.data.get(CONF_MONITORED_CAMERAS, [])

    entities: list[SwitchEntity] = [
        FallDetectorNotificationsMutedSwitch(coordinator),
    ]
    for camera in cameras:
        entities.append(CameraFallAlertsEnabledSwitch(coordinator, camera))

    async_add_entities(entities)


# ---------------------------------------------------------------------------
# Helper: shared device_info builders
# ---------------------------------------------------------------------------


def _system_device_info() -> dict:
    """Return device info for the global fall detector device."""
    return {
        "identifiers": {(DOMAIN, "fall_detector_system")},
        "name": "Fall Detector",
        "manufacturer": "Fall Detector",
        "model": "Fall Detection System",
    }


def _camera_device_info(camera_name: str) -> dict:
    """Return device info for a per-camera device."""
    return {
        "identifiers": {(DOMAIN, f"camera_{camera_name}")},
        "name": f"Fall Detector - {camera_name}",
        "manufacturer": "Fall Detector",
        "model": "Camera Monitor",
        "via_device": (DOMAIN, "fall_detector_system"),
    }


# ---------------------------------------------------------------------------
# Global switches
# ---------------------------------------------------------------------------


class FallDetectorNotificationsMutedSwitch(
    CoordinatorEntity[FallDetectorCoordinator], SwitchEntity
):
    """Switch to mute / unmute all fall-detector notifications."""

    _attr_has_entity_name = True
    _attr_device_class = SwitchDeviceClass.SWITCH
    _attr_icon = "mdi:bell-off-outline"

    def __init__(self, coordinator: FallDetectorCoordinator) -> None:
        """Initialize the switch."""
        super().__init__(coordinator)
        self._attr_unique_id = f"{DOMAIN}_notifications_muted"
        self._attr_name = "Fall Detector Notifications Muted"
        self._attr_device_info = _system_device_info()

    @property
    def is_on(self) -> bool | None:
        """Return true when notifications are muted."""
        if self.coordinator.data is None:
            return None
        return self.coordinator.data.notifications_muted

    async def async_turn_on(self, **kwargs: Any) -> None:
        """Mute notifications."""
        await self.coordinator.api.async_mute_notifications(True)
        await self.coordinator.async_request_refresh()

    async def async_turn_off(self, **kwargs: Any) -> None:
        """Unmute notifications."""
        await self.coordinator.api.async_mute_notifications(False)
        await self.coordinator.async_request_refresh()


# ---------------------------------------------------------------------------
# Per-camera switches
# ---------------------------------------------------------------------------


class CameraFallAlertsEnabledSwitch(
    CoordinatorEntity[FallDetectorCoordinator], SwitchEntity
):
    """Switch to enable / disable fall alerts for a specific camera."""

    _attr_has_entity_name = True
    _attr_device_class = SwitchDeviceClass.SWITCH
    _attr_icon = "mdi:bell-ring-outline"

    def __init__(
        self, coordinator: FallDetectorCoordinator, camera_name: str
    ) -> None:
        """Initialize the switch."""
        super().__init__(coordinator)
        self._camera_name = camera_name
        self._attr_unique_id = f"{DOMAIN}_{camera_name}_fall_alerts_enabled"
        self._attr_name = f"{camera_name} Fall Alerts Enabled"
        self._attr_device_info = _camera_device_info(camera_name)

    @property
    def is_on(self) -> bool | None:
        """Return true when fall alerts are enabled for the camera."""
        if self.coordinator.data is None:
            return None
        return self.coordinator.data.is_camera_alerts_enabled(self._camera_name)

    async def async_turn_on(self, **kwargs: Any) -> None:
        """Enable fall alerts for the camera."""
        await self.coordinator.api.async_set_camera_alerts(
            self._camera_name, enabled=True
        )
        await self.coordinator.async_request_refresh()

    async def async_turn_off(self, **kwargs: Any) -> None:
        """Disable fall alerts for the camera."""
        await self.coordinator.api.async_set_camera_alerts(
            self._camera_name, enabled=False
        )
        await self.coordinator.async_request_refresh()
