"""Test fixtures for integration tests."""
# SPDX-License-Identifier: Apache-2.0

from unittest.mock import AsyncMock, patch

import pytest

from custom_components.fall_detector.const import DOMAIN


@pytest.fixture
def mock_api():
    """Mock the FallDetectorApi."""
    with patch(
        "custom_components.fall_detector.coordinator.FallDetectorApi",
    ) as mock:
        api = mock.return_value
        api.async_get_health = AsyncMock(
            return_value={"status": "ok", "version": "0.1.0"}
        )
        api.async_get_status = AsyncMock(
            return_value={
                "online": True,
                "version": "0.1.0",
                "uptime_seconds": 3600.0,
                "cameras": {
                    "living_room": {
                        "camera_name": "living_room",
                        "monitoring_active": True,
                        "alerts_enabled": True,
                        "active_alert": False,
                        "last_fall_event": None,
                        "error_count": 0,
                    }
                },
                "active_alerts": 0,
                "total_events": 0,
                "last_event": None,
                "notifications_muted": False,
            }
        )
        api.async_get_recent_events = AsyncMock(return_value=[])
        api.async_test_alert = AsyncMock(return_value={"status": "ok"})
        api.async_acknowledge_alert = AsyncMock(return_value={"status": "ok"})
        api.async_mute_notifications = AsyncMock(return_value={"status": "ok"})
        api.async_unmute_notifications = AsyncMock(return_value={"status": "ok"})
        api.async_reset_camera = AsyncMock(return_value={"status": "ok"})
        api.async_reset_all = AsyncMock(return_value={"status": "ok"})
        api.async_close = AsyncMock()
        yield api


@pytest.fixture
def mock_config_entry():
    """Create a mock config entry."""
    from unittest.mock import MagicMock
    entry = MagicMock()
    entry.entry_id = "test_entry_id"
    entry.data = {
        "addon_url": "http://localhost:8099",
        "frigate_url": "http://localhost:5000",
        "monitored_cameras": ["living_room"],
    }
    entry.options = {}
    return entry
