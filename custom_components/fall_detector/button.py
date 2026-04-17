"""Button platform for Fall Detector."""
# SPDX-License-Identifier: Apache-2.0

from __future__ import annotations

import logging

from homeassistant.components.button import ButtonDeviceClass, ButtonEntity
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
    """Set up Fall Detector buttons."""
    coordinator: FallDetectorCoordinator = hass.data[DOMAIN][entry.entry_id]
    cameras: list[str] = entry.data.get(CONF_MONITORED_CAMERAS, [])

    entities: list[ButtonEntity] = [
        FallDetectorResetAllButton(coordinator),
    ]
    for camera in cameras:
        entities.append(CameraTestFallAlertButton(coordinator, camera))

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
# Global buttons
# ---------------------------------------------------------------------------


class FallDetectorResetAllButton(
    CoordinatorEntity[FallDetectorCoordinator], ButtonEntity
):
    """Button to reset all camera states and clear active alerts."""

    _attr_has_entity_name = True
    _attr_device_class = ButtonDeviceClass.RESTART
    _attr_icon = "mdi:refresh"

    def __init__(self, coordinator: FallDetectorCoordinator) -> None:
        """Initialize the button."""
        super().__init__(coordinator)
        self._attr_unique_id = f"{DOMAIN}_reset_all"
        self._attr_name = "Fall Detector Reset All"
        self._attr_device_info = _system_device_info()

    async def async_press(self) -> None:
        """Handle the button press."""
        _LOGGER.info("Resetting all Fall Detector camera states")
        await self.coordinator.api.async_reset_all()
        await self.coordinator.async_request_refresh()


# ---------------------------------------------------------------------------
# Per-camera buttons
# ---------------------------------------------------------------------------


class CameraTestFallAlertButton(
    CoordinatorEntity[FallDetectorCoordinator], ButtonEntity
):
    """Button to trigger a test fall alert on a specific camera."""

    _attr_has_entity_name = True
    _attr_icon = "mdi:alert-circle-check-outline"

    def __init__(
        self, coordinator: FallDetectorCoordinator, camera_name: str
    ) -> None:
        """Initialize the button."""
        super().__init__(coordinator)
        self._camera_name = camera_name
        self._attr_unique_id = f"{DOMAIN}_{camera_name}_test_fall_alert"
        self._attr_name = f"{camera_name} Test Fall Alert"
        self._attr_device_info = _camera_device_info(camera_name)

    async def async_press(self) -> None:
        """Handle the button press."""
        _LOGGER.info("Triggering test fall alert for camera %s", self._camera_name)
        await self.coordinator.api.async_test_alert(self._camera_name)
        await self.coordinator.async_request_refresh()
