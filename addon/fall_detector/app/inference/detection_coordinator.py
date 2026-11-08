"""Detection coordinator - orchestrates the fall detection pipeline."""
# SPDX-License-Identifier: Apache-2.0

from __future__ import annotations

import asyncio
import contextlib
from collections import deque
from datetime import datetime, timedelta

from app.config.settings import Settings
from app.fusion import SensorFusion
from app.inference.fall_scorer import FallScorer, ScoreResult, ScoringConfig
from app.inference.frame_source import FrameSource
from app.inference.pose_estimator import PoseEstimator
from app.models import (
    CameraState,
    DetectionStage,
    FallDetectionEvent,
    ReasonCode,
    SystemStatus,
)
from app.utils.logging import get_logger

logger = get_logger(__name__)


class DetectionCoordinator:
    """Coordinates the fall detection pipeline across cameras."""

    def __init__(
        self,
        settings: Settings,
        frame_source: FrameSource,
        pose_estimator: PoseEstimator,
        fusion: SensorFusion | None = None,
    ):
        self._settings = settings
        self._frame_source = frame_source
        self._pose_estimator = pose_estimator
        self._fusion = fusion
        self._scorer = FallScorer(
            config=ScoringConfig(
                confidence_threshold=settings.detection_confidence_threshold,
                fall_confirmation_seconds=settings.fall_confirmation_seconds,
                recovery_window_seconds=settings.recovery_window_seconds,
                alert_cooldown_seconds=settings.alert_cooldown_seconds,
            )
        )
        self._camera_states: dict[str, CameraState] = {}
        self._recent_events: deque[FallDetectionEvent] = deque(maxlen=100)
        self._running = False
        self._tasks: dict[str, asyncio.Task] = {}
        # Camera-confirmed falls awaiting sensor corroboration (require mode)
        self._pending_fusion: dict[str, tuple[ScoreResult, datetime]] = {}
        # Bumped on reset so an in-flight sensor query cannot resurrect an alert
        self._generation: dict[str, int] = {}
        self._start_time = datetime.utcnow()
        self._total_events = 0
        self._notifications_muted = False
        self._alert_callbacks: list = []
        self._event_callbacks: list = []

        # Initialize camera states
        for cam in settings.monitored_cameras:
            self._camera_states[cam] = CameraState(camera_name=cam)

    @property
    def pose_ready(self) -> bool:
        """Whether the pose model is loaded and ready for inference."""
        return self._pose_estimator.is_ready()

    @property
    def camera_states(self) -> dict[str, CameraState]:
        return self._camera_states

    @property
    def recent_events(self) -> list[FallDetectionEvent]:
        return list(self._recent_events)

    @property
    def notifications_muted(self) -> bool:
        return self._notifications_muted

    @notifications_muted.setter
    def notifications_muted(self, value: bool) -> None:
        self._notifications_muted = value

    def on_alert(self, callback) -> None:
        """Register a callback for confirmed fall alerts."""
        self._alert_callbacks.append(callback)

    def on_event(self, callback) -> None:
        """Register a callback for all detection events."""
        self._event_callbacks.append(callback)

    async def start(self) -> None:
        """Start monitoring all configured cameras."""
        if self._running:
            return

        await self._pose_estimator.initialize()
        self._running = True
        self._start_time = datetime.utcnow()

        for camera_name in self._settings.monitored_cameras:
            task = asyncio.create_task(
                self._monitor_camera(camera_name),
                name=f"monitor_{camera_name}",
            )
            self._tasks[camera_name] = task
            logger.info("camera_monitoring_started", camera=camera_name)

    async def stop(self) -> None:
        """Stop all monitoring tasks."""
        self._running = False
        for name, task in self._tasks.items():
            task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await task
            logger.info("camera_monitoring_stopped", camera=name)
        self._tasks.clear()
        if self._fusion:
            await self._fusion.close()

    async def _monitor_camera(self, camera_name: str) -> None:
        """Continuous monitoring loop for a single camera."""
        interval = 1.0 / max(self._settings.frame_sample_rate, 0.1)
        state = self._camera_states[camera_name]

        while self._running:
            try:
                if not state.monitoring_active:
                    await asyncio.sleep(interval)
                    continue

                # Get frame
                frame, timestamp = await self._frame_source.get_frame(camera_name)
                if frame is None:
                    state.error_count += 1
                    if state.error_count > 30:
                        logger.error("camera_stream_stale", camera=camera_name, errors=state.error_count)
                    await asyncio.sleep(interval)
                    continue

                state.error_count = 0
                state.frame_count += 1

                # Run pose estimation
                pose = await self._pose_estimator.estimate_pose(frame)

                # No person detected — skip scoring
                if pose is None:
                    # Reset fall candidate if no person visible
                    if state.fall_candidate_start is not None:
                        state.consecutive_fall_frames = 0
                        state.fall_candidate_start = None
                    self._pending_fusion.pop(camera_name, None)
                    await asyncio.sleep(interval)
                    continue

                state.last_person_detected = timestamp

                # Expire before scoring so the cooldown also rejects this frame
                self._expire_pending_fusion(camera_name, state, timestamp)

                # Score frame
                result = self._scorer.score_frame(
                    camera_name=camera_name,
                    pose=pose,
                    camera_state=state,
                    person_detected=True,
                )

                alert_event: FallDetectionEvent | None = None
                suppressed = False
                generation = self._generation.get(camera_name, 0)

                # Recovery cancels a pending fall before any re-confirmation
                if camera_name in self._pending_fusion and self._scorer.check_recovery(camera_name, pose):
                    self._pending_fusion.pop(camera_name)
                    state.consecutive_fall_frames = 0
                    state.fall_candidate_start = None
                    logger.info("pending_fusion_cleared_recovery", camera=camera_name)

                # Handle confirmed fall
                elif result.should_alert and result.stage == DetectionStage.CONFIRMED_FALL:
                    alert_event = await self._handle_confirmed_fall(camera_name, state, result, timestamp)
                    if self._generation.get(camera_name, 0) != generation:
                        pass  # reset during the sensor query; handled below
                    elif alert_event is None:
                        suppressed = True
                        self._pending_fusion.setdefault(camera_name, (result, timestamp))
                    else:
                        self._pending_fusion.pop(camera_name, None)

                # Retry a suppressed fall until the sensor agrees, the person
                # recovers, or the fusion window expires
                elif camera_name in self._pending_fusion:
                    alert_event, suppressed = await self._retry_pending_fusion(camera_name, state, timestamp)

                # Check for recovery on active alerts
                elif state.active_alert and pose is not None and self._scorer.check_recovery(camera_name, pose):
                    await self._handle_recovery(camera_name, state)

                # A reset during an awaited sensor query invalidates this frame
                if self._generation.get(camera_name, 0) != generation:
                    await asyncio.sleep(interval)
                    continue

                # Emit event for any significant stage
                event: FallDetectionEvent | None = alert_event
                if event is None and result.stage not in (DetectionStage.REJECTED, DetectionStage.PERSON_DETECTED):
                    stage = result.stage
                    if suppressed and stage == DetectionStage.CONFIRMED_FALL:
                        # Not confirmed until the sensor agrees
                        stage = DetectionStage.FALL_CONFIRMING
                    event = FallDetectionEvent(
                        camera=camera_name,
                        timestamp=timestamp,
                        confidence=result.confidence,
                        stage=stage,
                        pose_summary=result.pose_summary or pose,
                        motion_summary=result.motion_summary,
                        reason_codes=result.reason_codes,
                    )
                if event is not None:
                    for cb in self._event_callbacks:
                        try:
                            await cb(event)
                        except Exception:
                            logger.exception("event_callback_error")

                await asyncio.sleep(interval)

            except asyncio.CancelledError:
                break
            except Exception:
                logger.exception("monitoring_loop_error", camera=camera_name)
                await asyncio.sleep(interval * 2)  # Back off on error

    def _expire_pending_fusion(self, camera_name: str, state: CameraState, timestamp: datetime) -> None:
        """Drop a pending fall the sensor never confirmed within the window.

        The camera then cools down and the candidate is re-armed, so the same
        unchanged fall is not immediately queued again.
        """
        pending = self._pending_fusion.get(camera_name)
        if not pending or (timestamp - pending[1]).total_seconds() <= self._settings.fusion_window_seconds:
            return
        self._pending_fusion.pop(camera_name)
        state.consecutive_fall_frames = 0
        state.fall_candidate_start = None
        state.cooldown_until = datetime.utcnow() + timedelta(seconds=self._settings.alert_cooldown_seconds)
        logger.info("pending_fusion_expired", camera=camera_name)

    async def _retry_pending_fusion(
        self,
        camera_name: str,
        state: CameraState,
        timestamp: datetime,
    ) -> tuple[FallDetectionEvent | None, bool]:
        """Re-check a suppressed fall. Returns (alert_event, still_suppressed)."""
        result, _ = self._pending_fusion[camera_name]
        event = await self._handle_confirmed_fall(camera_name, state, result, timestamp)
        if event is None:
            return None, camera_name in self._pending_fusion  # False if a reset cleared it
        self._pending_fusion.pop(camera_name, None)
        return event, False

    async def _handle_confirmed_fall(
        self,
        camera_name: str,
        state: CameraState,
        result,
        timestamp: datetime,
    ) -> FallDetectionEvent | None:
        """Handle a confirmed fall. Returns the alert event, or None if fusion suppressed it."""
        reason_codes = list(result.reason_codes)
        confidence = result.confidence
        mode = self._settings.fusion_mode
        if mode != "off" and self._fusion and self._fusion.has_sensor(camera_name):
            generation = self._generation.get(camera_name, 0)
            agrees = await self._fusion.corroborate(camera_name)
            if self._generation.get(camera_name, 0) != generation:
                logger.info("fall_discarded_after_reset", camera=camera_name)
                return None
            if agrees:
                reason_codes.append(ReasonCode.SENSOR_CONFIRMED)
                confidence = min(confidence + 0.1, 1.0)
            elif agrees is None:
                # Fail open: an unreachable sensor must never hide a real fall
                reason_codes.append(ReasonCode.SENSOR_UNAVAILABLE)
            elif mode == "require":
                logger.info("fall_suppressed_by_fusion", camera=camera_name, confidence=confidence)
                return None

        self._total_events += 1

        event = FallDetectionEvent(
            camera=camera_name,
            timestamp=timestamp,
            confidence=confidence,
            stage=DetectionStage.CONFIRMED_FALL,
            pose_summary=result.pose_summary,
            motion_summary=result.motion_summary,
            reason_codes=reason_codes,
        )

        state.active_alert = True
        state.alert_acknowledged = False
        state.last_fall_event = event
        state.last_alert_time = datetime.utcnow()
        state.cooldown_until = datetime.utcnow() + timedelta(seconds=self._settings.alert_cooldown_seconds)

        self._recent_events.append(event)

        logger.warning(
            "fall_detected",
            camera=camera_name,
            confidence=event.confidence,
            reasons=[r.value for r in event.reason_codes],
            event_id=event.event_id,
        )

        # Fire alert callbacks
        if not self._notifications_muted and state.alerts_enabled:
            for cb in self._alert_callbacks:
                try:
                    await cb(event)
                except Exception:
                    logger.exception("alert_callback_error")

        return event

    async def _handle_recovery(self, camera_name: str, state: CameraState) -> None:
        """Handle recovery detection."""
        state.active_alert = False
        state.consecutive_fall_frames = 0
        state.fall_candidate_start = None

        logger.info("recovery_detected", camera=camera_name)

        event = FallDetectionEvent(
            camera=camera_name,
            timestamp=datetime.utcnow(),
            stage=DetectionStage.RECOVERY_DETECTED,
            recovery_detected=True,
            reason_codes=[ReasonCode.RECOVERY_MOVEMENT],
        )
        self._recent_events.append(event)

        for cb in self._event_callbacks:
            try:
                await cb(event)
            except Exception:
                logger.exception("event_callback_error")

    def acknowledge_alert(self, camera_name: str | None = None) -> bool:
        """Acknowledge an active alert."""
        if camera_name:
            state = self._camera_states.get(camera_name)
            if state and state.active_alert:
                state.alert_acknowledged = True
                state.active_alert = False
                state.consecutive_fall_frames = 0
                state.fall_candidate_start = None
                return True
            return False
        # Acknowledge all
        acknowledged = False
        for state in self._camera_states.values():
            if state.active_alert:
                state.alert_acknowledged = True
                state.active_alert = False
                state.consecutive_fall_frames = 0
                state.fall_candidate_start = None
                acknowledged = True
        return acknowledged

    def reset_camera_state(self, camera_name: str) -> bool:
        """Reset all state for a camera."""
        state = self._camera_states.get(camera_name)
        if not state:
            return False
        state.active_alert = False
        state.alert_acknowledged = False
        state.consecutive_fall_frames = 0
        state.fall_candidate_start = None
        self._pending_fusion.pop(camera_name, None)
        self._generation[camera_name] = self._generation.get(camera_name, 0) + 1
        state.cooldown_until = None
        state.error_count = 0
        self._scorer.reset_camera(camera_name)
        return True

    def reset_all(self) -> None:
        """Reset all camera states."""
        for name in list(self._camera_states.keys()):
            self.reset_camera_state(name)

    def get_system_status(self) -> SystemStatus:
        """Get overall system status."""
        uptime = (datetime.utcnow() - self._start_time).total_seconds()
        active_alerts = sum(1 for s in self._camera_states.values() if s.active_alert)
        return SystemStatus(
            online=self._running,
            uptime_seconds=uptime,
            cameras=self._camera_states,
            active_alerts=active_alerts,
            total_events=self._total_events,
            last_event=self._recent_events[-1] if self._recent_events else None,
            notifications_muted=self._notifications_muted,
        )

    async def create_test_alert(self, camera_name: str) -> FallDetectionEvent:
        """Create a test alert for validation."""
        event = FallDetectionEvent(
            camera=camera_name,
            confidence=0.99,
            stage=DetectionStage.CONFIRMED_FALL,
            reason_codes=[ReasonCode.PRONE_DWELL],
            debug={"test_alert": True},
        )
        self._recent_events.append(event)
        self._total_events += 1

        for cb in self._alert_callbacks:
            try:
                await cb(event)
            except Exception:
                logger.exception("test_alert_callback_error")

        return event
