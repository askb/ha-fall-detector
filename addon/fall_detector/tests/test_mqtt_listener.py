"""Tests for Frigate MQTT event parsing."""
# SPDX-License-Identifier: Apache-2.0

import pytest

from app.frigate.mqtt_listener import FrigateEventData


SAMPLE_FRIGATE_EVENT = {
    "type": "new",
    "before": {},
    "after": {
        "id": "1234567890.abcdef",
        "camera": "front_camera",
        "label": "person",
        "top_score": 0.85,
        "current_zones": ["driveway"],
        "has_snapshot": True,
        "has_clip": False,
        "start_time": 1700000000.0,
        "end_time": None,
        "stationary": False,
    },
}


class TestFrigateEventData:
    def test_parse_person_event(self):
        event = FrigateEventData(SAMPLE_FRIGATE_EVENT)
        assert event.camera == "front_camera"
        assert event.label == "person"
        assert event.is_person is True
        assert event.is_new is True
        assert event.is_active is True
        assert event.top_score == 0.85
        assert "driveway" in event.current_zones

    def test_parse_end_event(self):
        data = {**SAMPLE_FRIGATE_EVENT, "type": "end"}
        data["after"] = {**SAMPLE_FRIGATE_EVENT["after"], "end_time": 1700000030.0}
        event = FrigateEventData(data)
        assert event.is_end is True
        assert event.is_active is False

    def test_non_person_event(self):
        data = {**SAMPLE_FRIGATE_EVENT}
        data["after"] = {**SAMPLE_FRIGATE_EVENT["after"], "label": "car"}
        event = FrigateEventData(data)
        assert event.is_person is False

    def test_empty_event(self):
        event = FrigateEventData({"type": "", "before": {}, "after": {}})
        assert event.camera == ""
        assert event.is_person is False
