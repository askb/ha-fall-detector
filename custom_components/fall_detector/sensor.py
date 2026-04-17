"""Sensor platform for Fall Detector."""
# SPDX-License-Identifier: Apache-2.0

from __future__ import annotations

from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorStateClass,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import PERCENTAGE
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import CONF_MONITORED_CAMERAS, DOMAIN
from .coordinator import FallDetectorCoordinator


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up Fall Detector sensors."""
    coordinator: FallDetectorCoordinator = hass.data[DOMAIN][entry.entry_id]
    cameras: list[str] = entry.data.get(CONF_MONITORED_CAMERAS, [])

    entities: list[SensorEntity] = [
        FallDetectorActiveAlertsSensor(coordinator),
        FallDetectorLastEventSensor(coordinator),
    ]

    for camera in cameras:
        entities.extend(
            [
                CameraFallConfidenceSensor(coordinator, camera),
                CameraLastFallTimeSensor(coordinator, camera),
                CameraMonitorStatusSensor(coordinator, camera),
            ]
        )

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
# Global sensors
# ---------------------------------------------------------------------------


class FallDetectorActiveAlertsSensor(
    CoordinatorEntity[FallDetectorCoordinator], SensorEntity
):
    """Sensor showing the number of currently active fall alerts."""

    _attr_has_entity_name = True
    _attr_icon = "mdi:alert"
    _attr_state_class = SensorStateClass.MEASUREMENT
    _attr_native_unit_of_measurement = "alerts"

    def __init__(self, coordinator: FallDetectorCoordinator) -> None:
        """Initialize the sensor."""
        super().__init__(coordinator)
        self._attr_unique_id = f"{DOMAIN}_active_alerts"
        self._attr_name = "Fall Detector Active Alerts"
        self._attr_device_info = _system_device_info()

    @property
    def native_value(self) -> int | None:
        """Return the number of active alerts."""
        if self.coordinator.data is None:
            return None
        return self.coordinator.data.active_alerts


class FallDetectorLastEventSensor(
    CoordinatorEntity[FallDetectorCoordinator], SensorEntity
):
    """Sensor showing the timestamp of the last fall event."""

    _attr_has_entity_name = True
    _attr_device_class = SensorDeviceClass.TIMESTAMP
    _attr_icon = "mdi:clock-alert-outline"

    def __init__(self, coordinator: FallDetectorCoordinator) -> None:
        """Initialize the sensor."""
        super().__init__(coordinator)
        self._attr_unique_id = f"{DOMAIN}_last_event"
        self._attr_name = "Fall Detector Last Event"
        self._attr_device_info = _system_device_info()

    @property
    def native_value(self) -> str | None:
        """Return the ISO-8601 timestamp of the last event."""
        if self.coordinator.data is None:
            return None
        last = self.coordinator.data.last_event
        if last is None:
            return None
        return last.get("timestamp")

    @property
    def extra_state_attributes(self) -> dict:
        """Return additional attributes about the last event."""
        if self.coordinator.data is None:
            return {}
        last = self.coordinator.data.last_event
        if last is None:
            return {}
        return {
            "camera": last.get("camera"),
            "event_id": last.get("event_id"),
            "confidence": last.get("confidence"),
        }


# ---------------------------------------------------------------------------
# Per-camera sensors
# ---------------------------------------------------------------------------


class CameraFallConfidenceSensor(
    CoordinatorEntity[FallDetectorCoordinator], SensorEntity
):
    """Sensor showing the latest fall-detection confidence for a camera."""

    _attr_has_entity_name = True
    _attr_icon = "mdi:percent-circle"
    _attr_state_class = SensorStateClass.MEASUREMENT
    _attr_native_unit_of_measurement = PERCENTAGE
    _attr_suggested_display_precision = 1

    def __init__(
        self, coordinator: FallDetectorCoordinator, camera_name: str
    ) -> None:
        """Initialize the sensor."""
        super().__init__(coordinator)
        self._camera_name = camera_name
        self._attr_unique_id = f"{DOMAIN}_{camera_name}_fall_confidence"
        self._attr_name = f"{camera_name} Fall Confidence"
        self._attr_device_info = _camera_device_info(camera_name)

    @property
    def native_value(self) -> float | None:
        """Return the confidence percentage (0-100)."""
        if self.coordinator.data is None:
            return None
        return self.coordinator.data.get_camera_confidence(self._camera_name)


class CameraLastFallTimeSensor(
    CoordinatorEntity[FallDetectorCoordinator], SensorEntity
):
    """Sensor showing the timestamp of the last fall detected by a camera."""

    _attr_has_entity_name = True
    _attr_device_class = SensorDeviceClass.TIMESTAMP
    _attr_icon = "mdi:clock-outline"

    def __init__(
        self, coordinator: FallDetectorCoordinator, camera_name: str
    ) -> None:
        """Initialize the sensor."""
        super().__init__(coordinator)
        self._camera_name = camera_name
        self._attr_unique_id = f"{DOMAIN}_{camera_name}_last_fall_time"
        self._attr_name = f"{camera_name} Last Fall Time"
        self._attr_device_info = _camera_device_info(camera_name)

    @property
    def native_value(self) -> str | None:
        """Return the ISO-8601 timestamp of the last fall on this camera."""
        if self.coordinator.data is None:
            return None
        return self.coordinator.data.get_camera_last_fall_time(self._camera_name)


class CameraMonitorStatusSensor(
    CoordinatorEntity[FallDetectorCoordinator], SensorEntity
):
    """Sensor showing the monitoring status of a camera."""

    _attr_has_entity_name = True
    _attr_device_class = SensorDeviceClass.ENUM
    _attr_options = ["monitoring", "paused", "error", "unknown"]
    _attr_icon = "mdi:cctv"

    def __init__(
        self, coordinator: FallDetectorCoordinator, camera_name: str
    ) -> None:
        """Initialize the sensor."""
        super().__init__(coordinator)
        self._camera_name = camera_name
        self._attr_unique_id = f"{DOMAIN}_{camera_name}_monitor_status"
        self._attr_name = f"{camera_name} Monitor Status"
        self._attr_device_info = _camera_device_info(camera_name)

    @property
    def native_value(self) -> str | None:
        """Return the current monitoring status."""
        if self.coordinator.data is None:
            return None
        state = self.coordinator.data.get_camera_state(self._camera_name)
        if state is None:
            return "unknown"
        if state.get("error"):
            return "error"
        if self.coordinator.data.is_camera_monitoring(self._camera_name):
            return "monitoring"
        return "paused"

    @property
    def extra_state_attributes(self) -> dict:
        """Return additional status attributes."""
        if self.coordinator.data is None:
            return {}
        state = self.coordinator.data.get_camera_state(self._camera_name)
        if state is None:
            return {}
        attrs: dict = {}
        if state.get("error"):
            attrs["error_message"] = state.get("error")
        attrs["alerts_enabled"] = self.coordinator.data.is_camera_alerts_enabled(
            self._camera_name
        )
        return attrs
