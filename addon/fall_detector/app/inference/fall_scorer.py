"""Fall detection scoring engine with configurable heuristics."""
# SPDX-License-Identifier: Apache-2.0

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timedelta

from app.models import (
    CameraState,
    DetectionStage,
    FallDetectionEvent,
    MotionSummary,
    PoseSummary,
    ReasonCode,
)
from app.utils.logging import get_logger

logger = get_logger(__name__)


@dataclass
class ScoringConfig:
    """Configuration for fall scoring thresholds."""
    confidence_threshold: float = 0.7
    fall_confirmation_seconds: int = 5
    recovery_window_seconds: int = 30
    alert_cooldown_seconds: int = 120
    # Pose thresholds
    prone_angle_max: float = 30.0  # degrees from horizontal
    upright_angle_min: float = 50.0  # degrees from horizontal
    # Aspect ratio thresholds
    standing_aspect_min: float = 1.5  # height/width for standing person
    prone_aspect_max: float = 1.0  # height/width for lying person
    # Motion thresholds
    rapid_descent_threshold: float = 0.15  # normalized velocity
    # Minimum consecutive frames for candidate
    min_candidate_frames: int = 3


@dataclass
class ScoreResult:
    """Result of scoring a single frame."""
    stage: DetectionStage
    confidence: float
    reason_codes: list[ReasonCode] = field(default_factory=list)
    should_alert: bool = False
    pose_summary: PoseSummary | None = None
    motion_summary: MotionSummary | None = None


class FallScorer:
    """Scores frames for fall likelihood using a staged pipeline."""

    def __init__(self, config: ScoringConfig | None = None):
        self._config = config or ScoringConfig()
        self._previous_poses: dict[str, list[PoseSummary]] = {}
        self._pose_history_limit = 30

    def score_frame(
        self,
        camera_name: str,
        pose: PoseSummary | None,
        camera_state: CameraState,
        person_detected: bool = True,
        excluded_zones: list[str] | None = None,
    ) -> ScoreResult:
        """Score a single frame for fall likelihood."""
        reason_codes: list[ReasonCode] = []

        # Stage 1: Person gate
        if not person_detected:
            return ScoreResult(
                stage=DetectionStage.REJECTED,
                confidence=0.0,
                reason_codes=[ReasonCode.PERSON_GATE_FAILED],
            )

        # No pose data available
        if pose is None:
            return ScoreResult(
                stage=DetectionStage.PERSON_DETECTED,
                confidence=0.1,
            )

        # Store pose history for motion analysis
        if camera_name not in self._previous_poses:
            self._previous_poses[camera_name] = []
        history = self._previous_poses[camera_name]
        history.append(pose)
        if len(history) > self._pose_history_limit:
            history.pop(0)

        # Stage 2: Pose analysis
        confidence = 0.0
        motion = self._analyze_motion(camera_name)

        # Check torso angle
        if pose.torso_angle is not None:
            if pose.torso_angle < self._config.prone_angle_max:
                confidence += 0.35
                reason_codes.append(ReasonCode.TORSO_ANGLE_PRONE)
            elif pose.torso_angle < self._config.upright_angle_min:
                confidence += 0.15  # Partial lean

        # Check aspect ratio
        if pose.body_aspect_ratio is not None:
            if pose.body_aspect_ratio < self._config.prone_aspect_max:
                confidence += 0.25
                reason_codes.append(ReasonCode.ASPECT_RATIO_CHANGE)

        # Check rapid descent
        if motion.is_rapid_descent:
            confidence += 0.25
            reason_codes.append(ReasonCode.RAPID_DESCENT)

        # Cap at 1.0
        confidence = min(confidence, 1.0)

        # Determine stage
        now = datetime.utcnow()

        # Check cooldown
        if camera_state.cooldown_until and now < camera_state.cooldown_until:
            return ScoreResult(
                stage=DetectionStage.REJECTED,
                confidence=confidence,
                reason_codes=[ReasonCode.COOLDOWN_ACTIVE],
                pose_summary=pose,
                motion_summary=motion,
            )

        # Below threshold
        if confidence < self._config.confidence_threshold:
            # Reset candidate tracking if confidence drops
            if camera_state.consecutive_fall_frames > 0 and confidence < 0.3:
                camera_state.consecutive_fall_frames = 0
                camera_state.fall_candidate_start = None
            below_threshold_codes = list(reason_codes)
            if confidence > 0.2:
                below_threshold_codes.append(ReasonCode.LOW_CONFIDENCE_REJECTED)
            return ScoreResult(
                stage=DetectionStage.POSE_ESTIMATED if pose.pose_confidence > 0.3 else DetectionStage.PERSON_DETECTED,
                confidence=confidence,
                reason_codes=below_threshold_codes,
                pose_summary=pose,
                motion_summary=motion,
            )

        # Fall candidate tracking
        camera_state.consecutive_fall_frames += 1

        if camera_state.consecutive_fall_frames < self._config.min_candidate_frames:
            return ScoreResult(
                stage=DetectionStage.FALL_CANDIDATE,
                confidence=confidence,
                reason_codes=reason_codes,
                pose_summary=pose,
                motion_summary=motion,
            )

        # Start confirmation timer
        if camera_state.fall_candidate_start is None:
            camera_state.fall_candidate_start = now

        elapsed = (now - camera_state.fall_candidate_start).total_seconds()

        if elapsed < self._config.fall_confirmation_seconds:
            return ScoreResult(
                stage=DetectionStage.FALL_CONFIRMING,
                confidence=confidence,
                reason_codes=reason_codes,
                pose_summary=pose,
                motion_summary=motion,
            )

        # Confirmed fall - check for dwell
        reason_codes.append(ReasonCode.PRONE_DWELL)

        # Check if within recovery window but no recovery seen
        if elapsed > self._config.recovery_window_seconds:
            reason_codes.append(ReasonCode.NO_RECOVERY)
            confidence = min(confidence + 0.1, 1.0)

        return ScoreResult(
            stage=DetectionStage.CONFIRMED_FALL,
            confidence=confidence,
            reason_codes=reason_codes,
            should_alert=True,
            pose_summary=pose,
            motion_summary=motion,
        )

    def check_recovery(self, camera_name: str, pose: PoseSummary | None) -> bool:
        """Check if person has recovered (returned to upright position)."""
        if pose is None:
            return False
        if pose.torso_angle is not None and pose.torso_angle > self._config.upright_angle_min:
            return True
        if pose.body_aspect_ratio is not None and pose.body_aspect_ratio > self._config.standing_aspect_min:
            return True
        return False

    def _analyze_motion(self, camera_name: str) -> MotionSummary:
        """Analyze motion from pose history."""
        history = self._previous_poses.get(camera_name, [])
        if len(history) < 2:
            return MotionSummary()

        current = history[-1]
        previous = history[-2]

        # Calculate centroid movement from body aspect ratio changes
        # (simplified when we don't have absolute positions)
        vertical_displacement = 0.0
        velocity = 0.0
        is_rapid = False

        if current.torso_angle is not None and previous.torso_angle is not None:
            angle_change = previous.torso_angle - current.torso_angle
            velocity = abs(angle_change) / 90.0  # Normalize
            vertical_displacement = angle_change / 90.0
            is_rapid = velocity > self._config.rapid_descent_threshold

        direction = "unknown"
        if vertical_displacement > 0.05:
            direction = "downward"
        elif vertical_displacement < -0.05:
            direction = "upward"
        else:
            direction = "stable"

        return MotionSummary(
            centroid_velocity=velocity,
            vertical_displacement=vertical_displacement,
            direction=direction,
            is_rapid_descent=is_rapid,
        )

    def reset_camera(self, camera_name: str) -> None:
        """Reset scoring state for a camera."""
        self._previous_poses.pop(camera_name, None)
