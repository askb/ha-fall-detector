"""Binary sensor platform for Fall Detector."""
# SPDX-License-Identifier: Apache-2.0

from __future__ import annotations

from homeassistant.components.binary_sensor import (
    BinarySensorDeviceClass,
    BinarySensorEntity,
)
from homeassistant.config_entries import ConfigEntry
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
    """Set up Fall Detector binary sensors."""
    coordinator: FallDetectorCoordinator = hass.data[DOMAIN][entry.entry_id]
    cameras: list[str] = entry.data.get(CONF_MONITORED_CAMERAS, [])

    entities: list[BinarySensorEntity] = [FallDetectorOnlineSensor(coordinator)]
    for camera in cameras:
        entities.append(CameraFallDetectedSensor(coordinator, camera))

    async_add_entities(entities)


class FallDetectorOnlineSensor(
    CoordinatorEntity[FallDetectorCoordinator], BinarySensorEntity
):
    """Binary sensor for Fall Detector add-on online status."""

    _attr_has_entity_name = True
    _attr_device_class = BinarySensorDeviceClass.CONNECTIVITY

    def __init__(self, coordinator: FallDetectorCoordinator) -> None:
        """Initialize the sensor."""
        super().__init__(coordinator)
        self._attr_unique_id = f"{DOMAIN}_online"
        self._attr_name = "Fall Detector Online"
        self._attr_device_info = {
            "identifiers": {(DOMAIN, "fall_detector_system")},
            "name": "Fall Detector",
            "manufacturer": "Fall Detector",
            "model": "Fall Detection System",
        }

    @property
    def is_on(self) -> bool | None:
        """Return true if the add-on is online."""
        if self.coordinator.data is None:
            return False
        return self.coordinator.data.online


class CameraFallDetectedSensor(
    CoordinatorEntity[FallDetectorCoordinator], BinarySensorEntity
):
    """Binary sensor for fall detection on a specific camera."""

    _attr_has_entity_name = True
    _attr_device_class = BinarySensorDeviceClass.SAFETY

    def __init__(
        self, coordinator: FallDetectorCoordinator, camera_name: str
    ) -> None:
        """Initialize the sensor."""
        super().__init__(coordinator)
        self._camera_name = camera_name
        self._attr_unique_id = f"{DOMAIN}_{camera_name}_fall_detected"
        self._attr_name = f"{camera_name} Fall Detected"
        self._attr_device_info = {
            "identifiers": {(DOMAIN, f"camera_{camera_name}")},
            "name": f"Fall Detector - {camera_name}",
            "manufacturer": "Fall Detector",
            "model": "Camera Monitor",
            "via_device": (DOMAIN, "fall_detector_system"),
        }

    @property
    def is_on(self) -> bool | None:
        """Return true if a fall is actively detected."""
        if self.coordinator.data is None:
            return None
        return self.coordinator.data.is_camera_alerting(self._camera_name)

    @property
    def extra_state_attributes(self) -> dict:
        """Return additional attributes."""
        if self.coordinator.data is None:
            return {}
        state = self.coordinator.data.get_camera_state(self._camera_name)
        if not state:
            return {}
        last_event = state.get("last_fall_event")
        attrs: dict = {}
        if last_event:
            attrs["confidence"] = last_event.get("confidence", 0.0)
            attrs["reason_codes"] = last_event.get("reason_codes", [])
            attrs["event_id"] = last_event.get("event_id")
        return attrs
