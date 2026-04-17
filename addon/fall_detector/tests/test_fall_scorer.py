"""Tests for the fall scoring engine."""
# SPDX-License-Identifier: Apache-2.0

from datetime import datetime, timedelta

import pytest

from app.inference.fall_scorer import FallScorer, ScoringConfig
from app.models import (
    CameraState,
    DetectionStage,
    Keypoint,
    MotionSummary,
    PoseSummary,
    ReasonCode,
)


class TestFallScorerPersonGate:
    """Tests for person detection gate."""

    def test_no_person_returns_rejected(self, fall_scorer: FallScorer, camera_state: CameraState):
        result = fall_scorer.score_frame(
            camera_name="test_camera",
            pose=None,
            camera_state=camera_state,
            person_detected=False,
        )
        assert result.stage == DetectionStage.REJECTED
        assert ReasonCode.PERSON_GATE_FAILED in result.reason_codes

    def test_person_with_no_pose_returns_detected(self, fall_scorer: FallScorer, camera_state: CameraState):
        result = fall_scorer.score_frame(
            camera_name="test_camera",
            pose=None,
            camera_state=camera_state,
            person_detected=True,
        )
        assert result.stage == DetectionStage.PERSON_DETECTED
        assert result.confidence == 0.1


class TestFallScorerPoseAnalysis:
    """Tests for pose-based fall detection."""

    def test_upright_pose_low_confidence(self, fall_scorer: FallScorer, camera_state: CameraState):
        """Standing person should not trigger fall."""
        pose = PoseSummary(
            torso_angle=80.0,  # Nearly vertical
            body_aspect_ratio=2.5,  # Tall and narrow = standing
            pose_confidence=0.8,
        )
        result = fall_scorer.score_frame(
            camera_name="test_camera",
            pose=pose,
            camera_state=camera_state,
        )
        assert result.confidence < 0.7
        assert not result.should_alert

    def test_prone_pose_high_confidence(self, fall_scorer: FallScorer, camera_state: CameraState):
        """Person lying flat should score high."""
        pose = PoseSummary(
            torso_angle=15.0,  # Nearly horizontal
            body_aspect_ratio=0.5,  # Wide and short = lying down
            pose_confidence=0.8,
        )
        result = fall_scorer.score_frame(
            camera_name="test_camera",
            pose=pose,
            camera_state=camera_state,
        )
        assert result.confidence >= 0.5
        assert ReasonCode.TORSO_ANGLE_PRONE in result.reason_codes

    def test_partial_lean_moderate_confidence(self, fall_scorer: FallScorer, camera_state: CameraState):
        """Leaning person should get moderate confidence."""
        pose = PoseSummary(
            torso_angle=40.0,  # Leaning
            body_aspect_ratio=1.2,
            pose_confidence=0.7,
        )
        result = fall_scorer.score_frame(
            camera_name="test_camera",
            pose=pose,
            camera_state=camera_state,
        )
        assert 0.1 < result.confidence < 0.7


class TestFallScorerConfirmation:
    """Tests for fall confirmation logic."""

    def test_requires_multiple_frames(self, fall_scorer: FallScorer, camera_state: CameraState):
        """Fall must persist across multiple frames before confirming."""
        prone_pose = PoseSummary(
            torso_angle=10.0,
            body_aspect_ratio=0.4,
            pose_confidence=0.9,
        )

        # First frame: should be candidate, not confirmed
        result = fall_scorer.score_frame("test_camera", prone_pose, camera_state)
        assert result.stage in (DetectionStage.FALL_CANDIDATE, DetectionStage.POSE_ESTIMATED)
        assert not result.should_alert

    def test_cooldown_prevents_repeated_alerts(self, fall_scorer: FallScorer, camera_state: CameraState):
        """Cooldown should prevent spam alerts."""
        camera_state.cooldown_until = datetime.utcnow() + timedelta(seconds=60)

        pose = PoseSummary(torso_angle=10.0, body_aspect_ratio=0.4, pose_confidence=0.9)
        result = fall_scorer.score_frame("test_camera", pose, camera_state)
        assert result.stage == DetectionStage.REJECTED
        assert ReasonCode.COOLDOWN_ACTIVE in result.reason_codes


class TestFallScorerRecovery:
    """Tests for recovery detection."""

    def test_upright_recovery(self, fall_scorer: FallScorer):
        """Person returning to upright should be detected as recovery."""
        upright_pose = PoseSummary(torso_angle=75.0, body_aspect_ratio=2.0, pose_confidence=0.8)
        assert fall_scorer.check_recovery("test_camera", upright_pose) is True

    def test_still_prone_no_recovery(self, fall_scorer: FallScorer):
        """Person still lying should not be recovery."""
        prone_pose = PoseSummary(torso_angle=15.0, body_aspect_ratio=0.5, pose_confidence=0.8)
        assert fall_scorer.check_recovery("test_camera", prone_pose) is False

    def test_no_pose_no_recovery(self, fall_scorer: FallScorer):
        """No pose data should not count as recovery."""
        assert fall_scorer.check_recovery("test_camera", None) is False


class TestFallScorerReset:
    """Tests for state reset."""

    def test_reset_clears_history(self, fall_scorer: FallScorer, camera_state: CameraState):
        """Reset should clear pose history."""
        pose = PoseSummary(torso_angle=50.0, pose_confidence=0.7)
        fall_scorer.score_frame("test_camera", pose, camera_state)
        fall_scorer.reset_camera("test_camera")
        assert "test_camera" not in fall_scorer._previous_poses


class TestFalsePositiveRegression:
    """Regression tests for common false positive scenarios."""

    def test_sitting_down_quickly(self, fall_scorer: FallScorer, camera_state: CameraState):
        """Sitting down should not trigger a confirmed fall (single frame)."""
        # Intermediate sitting angle
        sitting_pose = PoseSummary(
            torso_angle=55.0,  # Seated but torso is angled
            body_aspect_ratio=1.1,
            pose_confidence=0.7,
        )
        result = fall_scorer.score_frame("test_camera", sitting_pose, camera_state)
        assert not result.should_alert

    def test_lying_on_couch_aspect_ratio(self, fall_scorer: FallScorer, camera_state: CameraState):
        """Person on couch - single frame should not alert."""
        couch_pose = PoseSummary(
            torso_angle=20.0,
            body_aspect_ratio=0.6,
            pose_confidence=0.6,
        )
        result = fall_scorer.score_frame("test_camera", couch_pose, camera_state)
        # Should be candidate at most, not confirmed
        assert result.stage != DetectionStage.CONFIRMED_FALL

    def test_bending_to_pick_up(self, fall_scorer: FallScorer, camera_state: CameraState):
        """Bending down should have low/moderate confidence."""
        bending_pose = PoseSummary(
            torso_angle=35.0,  # Bent over
            body_aspect_ratio=1.0,
            pose_confidence=0.6,
        )
        result = fall_scorer.score_frame("test_camera", bending_pose, camera_state)
        assert not result.should_alert

    def test_low_confidence_pose_rejected(self, fall_scorer: FallScorer, camera_state: CameraState):
        """Very low confidence pose data should be handled gracefully."""
        low_conf_pose = PoseSummary(
            torso_angle=10.0,
            body_aspect_ratio=0.4,
            pose_confidence=0.1,
        )
        result = fall_scorer.score_frame("test_camera", low_conf_pose, camera_state)
        # Should still score based on angle/ratio but overall result may vary
        assert result.stage != DetectionStage.CONFIRMED_FALL
