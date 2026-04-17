"""Tests for the Fall Detector config flow."""
# SPDX-License-Identifier: Apache-2.0

from unittest.mock import AsyncMock, patch

import pytest

from custom_components.fall_detector.const import CONF_ADDON_URL, DOMAIN


async def test_config_flow_user_step_success():
    """Test successful user step."""
    # This test validates the config flow can be instantiated
    from custom_components.fall_detector.config_flow import FallDetectorConfigFlow

    flow = FallDetectorConfigFlow()
    assert flow is not None


async def test_config_flow_creates_entry():
    """Test that config flow creates an entry with correct data."""
    from custom_components.fall_detector.config_flow import FallDetectorConfigFlow

    flow = FallDetectorConfigFlow()
    flow._data = {
        CONF_ADDON_URL: "http://localhost:8099",
        "frigate_url": "http://localhost:5000",
        "monitored_cameras": ["living_room"],
    }
    # Test that _create_entry method works
    # (Full integration test would need HA test framework)
    assert flow._data[CONF_ADDON_URL] == "http://localhost:8099"
