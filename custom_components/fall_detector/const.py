"""Constants for the Fall Detector integration."""
# SPDX-License-Identifier: Apache-2.0

from __future__ import annotations

from typing import Final

DOMAIN: Final = "fall_detector"
DEFAULT_NAME: Final = "Fall Detector"
DEFAULT_ADDON_URL: Final = "http://localhost:8099"
DEFAULT_SCAN_INTERVAL: Final = 5  # seconds

# Config keys
CONF_ADDON_URL: Final = "addon_url"
CONF_FRIGATE_URL: Final = "frigate_url"
CONF_MONITORED_CAMERAS: Final = "monitored_cameras"
CONF_NOTIFICATION_TARGETS: Final = "notification_targets"
CONF_CONFIDENCE_THRESHOLD: Final = "confidence_threshold"
CONF_ALERT_COOLDOWN: Final = "alert_cooldown"
CONF_FALL_CONFIRMATION: Final = "fall_confirmation"
CONF_RECOVERY_WINDOW: Final = "recovery_window"
CONF_ESCALATION_ENABLED: Final = "escalation_enabled"
CONF_QUIET_HOURS_START: Final = "quiet_hours_start"
CONF_QUIET_HOURS_END: Final = "quiet_hours_end"
CONF_DEBUG_LOGGING: Final = "debug_logging"

# Platforms
PLATFORMS: Final = ["binary_sensor", "sensor", "switch", "button"]

# Events
EVENT_FALL_DETECTED: Final = f"{DOMAIN}.fall_detected"
EVENT_ALERT_ACKNOWLEDGED: Final = f"{DOMAIN}.alert_acknowledged"
EVENT_PERSON_RECOVERED: Final = f"{DOMAIN}.person_recovered"
EVENT_DETECTOR_FAULT: Final = f"{DOMAIN}.detector_fault"

# Services
SERVICE_TEST_ALERT: Final = "test_alert"
SERVICE_ACKNOWLEDGE_ALERT: Final = "acknowledge_alert"
SERVICE_MUTE_NOTIFICATIONS: Final = "mute_notifications"
SERVICE_UNMUTE_NOTIFICATIONS: Final = "unmute_notifications"
SERVICE_RESET_CAMERA_STATE: Final = "reset_camera_state"
SERVICE_TRIGGER_REANALYSIS: Final = "trigger_reanalysis"

# Attributes
ATTR_CAMERA: Final = "camera"
ATTR_CONFIDENCE: Final = "confidence"
ATTR_REASON_CODES: Final = "reason_codes"
ATTR_EVENT_ID: Final = "event_id"
ATTR_ESCALATION_LEVEL: Final = "escalation_level"
