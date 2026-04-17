"""Tests for data models."""
# SPDX-License-Identifier: Apache-2.0

from datetime import datetime

from app.models import (
    CameraState,
    DetectionStage,
    FallDetectionEvent,
    HealthResponse,
    Keypoint,
    MotionSummary,
    PoseSummary,
    ReasonCode,
    SystemStatus,
)


class TestFallDetectionEvent:
    def test_default_event_creation(self):
        event = FallDetectionEvent(camera="living_room")
        assert event.camera == "living_room"
        assert event.event_id  # UUID should be generated
        assert event.stage == DetectionStage.PERSON_DETECTED
        assert event.confidence == 0.0
        assert event.reason_codes == []

    def test_full_event_creation(self):
        event = FallDetectionEvent(
            camera="bedroom",
            confidence=0.92,
            stage=DetectionStage.CONFIRMED_FALL,
            reason_codes=[ReasonCode.RAPID_DESCENT, ReasonCode.PRONE_DWELL],
            frigate_event_id="abc123",
        )
        assert event.confidence == 0.92
        assert len(event.reason_codes) == 2
        assert event.frigate_event_id == "abc123"

    def test_event_serialization(self):
        event = FallDetectionEvent(camera="test")
        data = event.model_dump()
        assert "event_id" in data
        assert "camera" in data
        assert "timestamp" in data


class TestPoseSummary:
    def test_default_pose(self):
        pose = PoseSummary()
        assert pose.keypoints == []
        assert pose.torso_angle is None
        assert pose.pose_confidence == 0.0

    def test_pose_with_keypoints(self):
        kp = Keypoint(name="nose", x=0.5, y=0.3, confidence=0.9)
        pose = PoseSummary(keypoints=[kp], torso_angle=75.0, is_upright=True)
        assert len(pose.keypoints) == 1
        assert pose.is_upright is True


class TestCameraState:
    def test_default_state(self):
        state = CameraState(camera_name="test")
        assert state.monitoring_active is True
        assert state.alerts_enabled is True
        assert state.active_alert is False
        assert state.frame_count == 0
        assert state.error_count == 0


class TestSystemStatus:
    def test_default_status(self):
        status = SystemStatus()
        assert status.online is True
        assert status.active_alerts == 0
        assert status.cameras == {}


class TestHealthResponse:
    def test_health_response(self):
        health = HealthResponse(cameras_monitored=3, cameras_online=2)
        assert health.status == "ok"
        assert health.cameras_monitored == 3
