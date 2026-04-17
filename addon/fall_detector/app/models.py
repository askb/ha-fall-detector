# SPDX-License-Identifier: Apache-2.0
# SPDX-FileCopyrightText: 2025 The Linux Foundation
"""Data models for the fall detection system."""

from __future__ import annotations

import uuid
from datetime import datetime
from enum import StrEnum
from typing import Any

from pydantic import BaseModel, Field


class DetectionStage(StrEnum):
    """Stages of fall detection pipeline."""

    PERSON_DETECTED = "person_detected"
    POSE_ESTIMATED = "pose_estimated"
    FALL_CANDIDATE = "fall_candidate"
    FALL_CONFIRMING = "fall_confirming"
    CONFIRMED_FALL = "confirmed_fall"
    RECOVERY_DETECTED = "recovery_detected"
    REJECTED = "rejected"


class ReasonCode(StrEnum):
    """Explainability reason codes for detection decisions."""

    RAPID_DESCENT = "RAPID_DESCENT"
    PRONE_DWELL = "PRONE_DWELL"
    NO_RECOVERY = "NO_RECOVERY"
    ASPECT_RATIO_CHANGE = "ASPECT_RATIO_CHANGE"
    TORSO_ANGLE_PRONE = "TORSO_ANGLE_PRONE"
    LOW_CONFIDENCE_REJECTED = "LOW_CONFIDENCE_REJECTED"
    BED_ZONE_EXCLUDED = "BED_ZONE_EXCLUDED"
    SOFA_ZONE_EXCLUDED = "SOFA_ZONE_EXCLUDED"
    COOLDOWN_ACTIVE = "COOLDOWN_ACTIVE"
    PERSON_GATE_FAILED = "PERSON_GATE_FAILED"
    RECOVERY_MOVEMENT = "RECOVERY_MOVEMENT"


class Keypoint(BaseModel):
    """A single body keypoint from pose estimation."""

    name: str
    x: float
    y: float
    confidence: float


class PoseSummary(BaseModel):
    """Summary of pose estimation results."""

    keypoints: list[Keypoint] = Field(default_factory=list)
    torso_angle: float | None = None
    is_upright: bool | None = None
    is_prone: bool | None = None
    body_aspect_ratio: float | None = None
    pose_confidence: float = 0.0


class MotionSummary(BaseModel):
    """Summary of motion analysis."""

    centroid_velocity: float = 0.0
    vertical_displacement: float = 0.0
    direction: str = "unknown"
    is_rapid_descent: bool = False


class FallDetectionEvent(BaseModel):
    """A structured fall detection event."""

    event_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    camera: str
    timestamp: datetime = Field(default_factory=datetime.utcnow)
    confidence: float = 0.0
    stage: DetectionStage = DetectionStage.PERSON_DETECTED
    person_detected: bool = True
    pose_summary: PoseSummary = Field(default_factory=PoseSummary)
    motion_summary: MotionSummary = Field(default_factory=MotionSummary)
    recovery_detected: bool = False
    frigate_event_id: str | None = None
    snapshot_url: str | None = None
    clip_url: str | None = None
    reason_codes: list[ReasonCode] = Field(default_factory=list)
    debug: dict[str, Any] = Field(default_factory=dict)


class CameraState(BaseModel):
    """Runtime state for a single monitored camera."""

    camera_name: str
    monitoring_active: bool = True
    alerts_enabled: bool = True
    last_person_detected: datetime | None = None
    last_fall_event: FallDetectionEvent | None = None
    active_alert: bool = False
    alert_acknowledged: bool = False
    consecutive_fall_frames: int = 0
    fall_candidate_start: datetime | None = None
    last_alert_time: datetime | None = None
    cooldown_until: datetime | None = None
    frame_count: int = 0
    error_count: int = 0


class SystemStatus(BaseModel):
    """Overall system status."""

    online: bool = True
    version: str = "0.1.0"
    uptime_seconds: float = 0.0
    cameras: dict[str, CameraState] = Field(default_factory=dict)
    active_alerts: int = 0
    total_events: int = 0
    last_event: FallDetectionEvent | None = None
    notifications_muted: bool = False


class HealthResponse(BaseModel):
    """Health check response."""

    status: str = "ok"
    version: str = "0.1.0"
    uptime_seconds: float = 0.0
    cameras_monitored: int = 0
    cameras_online: int = 0


class AlertAction(StrEnum):
    """Actions that can be taken on an alert."""

    ACKNOWLEDGE = "acknowledge"
    MUTE = "mute"
    UNMUTE = "unmute"
    RESET = "reset"
    TEST = "test"
