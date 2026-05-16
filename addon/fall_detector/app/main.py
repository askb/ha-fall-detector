# SPDX-License-Identifier: Apache-2.0
# SPDX-FileCopyrightText: 2025 The Linux Foundation
"""Fall Detector – FastAPI application entry-point.

Wires together configuration, logging, MQTT/Frigate clients, the detection
coordinator, and exposes the REST API consumed by the ingress panel and
Home Assistant automations.
"""

from __future__ import annotations

import asyncio
import time
from collections import deque
from contextlib import asynccontextmanager
from datetime import datetime, timedelta
from typing import AsyncIterator

import uvicorn
from fastapi import Depends, FastAPI, HTTPException, Response
from fastapi.responses import JSONResponse

from app.alerts.manager import AlertManager
from app.alerts.mqtt_publisher import MqttPublisher
from app.config.settings import Settings
from app.inference.detection_coordinator import DetectionCoordinator
from app.inference.frame_source import FrigateFrameSource
from app.inference.pose_estimator import MoveNetEstimator
from app.models import (
    AlertAction,
    CameraState,
    DetectionStage,
    FallDetectionEvent,
    HealthResponse,
    MotionSummary,
    PoseSummary,
    ReasonCode,
    SystemStatus,
)
from app.utils.logging import get_logger, setup_logging

# ---------------------------------------------------------------------------
# Global application state
# ---------------------------------------------------------------------------

MAX_RECENT_EVENTS = 50


class AppState:
    """Mutable runtime state shared across the application."""

    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self.start_time: float = time.monotonic()
        self.logger = get_logger("app.state")

        # Core components (created in start())
        self.coordinator: DetectionCoordinator | None = None
        self.mqtt_publisher: MqttPublisher | None = None
        self.alert_manager: AlertManager | None = None
        self.frame_source: FrigateFrameSource | None = None

    # -- properties delegating to coordinator --------------------------------

    @property
    def uptime(self) -> float:
        return time.monotonic() - self.start_time

    @property
    def cameras(self) -> dict[str, CameraState]:
        if self.coordinator:
            return self.coordinator.camera_states
        return {}

    @property
    def recent_events(self) -> list[FallDetectionEvent]:
        if self.coordinator:
            return self.coordinator.recent_events
        return []

    @property
    def total_events(self) -> int:
        if self.coordinator:
            return self.coordinator._total_events
        return 0

    @property
    def active_alerts(self) -> int:
        return sum(
            1
            for cam in self.cameras.values()
            if cam.active_alert and not cam.alert_acknowledged
        )

    @property
    def last_event(self) -> FallDetectionEvent | None:
        events = self.recent_events
        return events[-1] if events else None

    @property
    def notifications_muted(self) -> bool:
        if self.coordinator:
            return self.coordinator.notifications_muted
        return False

    @notifications_muted.setter
    def notifications_muted(self, value: bool) -> None:
        if self.coordinator:
            self.coordinator.notifications_muted = value

    def get_camera(self, name: str) -> CameraState:
        cams = self.cameras
        if name not in cams:
            raise HTTPException(status_code=404, detail=f"Camera '{name}' not found")
        return cams[name]

    # -- lifecycle -----------------------------------------------------------

    async def start(self) -> None:
        """Create components, wire callbacks, and start the detection pipeline."""
        # Frame source
        self.frame_source = FrigateFrameSource(
            frigate_url=self.settings.frigate_url,
        )

        # Pose estimator — select backend based on config
        if self.settings.pose_backend.startswith("yolo_pose"):
            from app.inference.pose_estimator import YoloPoseEstimator

            pose_estimator = YoloPoseEstimator(
                model_variant=self.settings.pose_backend,
                model_dir=f"{self.settings.fall_detector_data_path}/models",
            )
        else:
            pose_estimator = MoveNetEstimator(
                model_variant=self.settings.pose_backend,
                model_dir=f"{self.settings.fall_detector_data_path}/models",
            )

        # Detection coordinator
        self.coordinator = DetectionCoordinator(
            settings=self.settings,
            frame_source=self.frame_source,
            pose_estimator=pose_estimator,
        )

        # MQTT publisher
        self.mqtt_publisher = MqttPublisher(
            host=self.settings.mqtt_host,
            port=self.settings.mqtt_port,
            username=self.settings.mqtt_username or None,
            password=self.settings.mqtt_password or None,
        )

        # Alert manager
        self.alert_manager = AlertManager(
            cooldown_seconds=self.settings.alert_cooldown_seconds,
        )

        # Wire callbacks
        async def on_alert(event: FallDetectionEvent) -> None:
            """Handle confirmed fall alerts."""
            if self.mqtt_publisher:
                await self.mqtt_publisher.publish_fall_event(event)
                await self.mqtt_publisher.notify_alert(event, escalation_level=0)
            if self.alert_manager:
                await self.alert_manager.process_alert(event)

        async def on_event(event: FallDetectionEvent) -> None:
            """Handle all detection events."""
            if self.mqtt_publisher:
                await self.mqtt_publisher.publish_fall_event(event)

        async def on_escalation(event: FallDetectionEvent, level: int) -> None:
            """Handle escalation notifications."""
            if self.mqtt_publisher:
                await self.mqtt_publisher.notify_alert(event, escalation_level=level)

        self.coordinator.on_alert(on_alert)
        self.coordinator.on_event(on_event)
        self.alert_manager.on_notification(on_escalation)

        # Connect MQTT
        try:
            await self.mqtt_publisher.connect()
            await self.mqtt_publisher.publish_availability(online=True)
        except Exception:
            self.logger.exception("mqtt_connect_failed")

        # Start detection pipeline
        await self.coordinator.start()

        self.logger.info(
            "pipeline_started",
            cameras=len(self.cameras),
            pose_backend=self.settings.pose_backend,
            frigate_url=self.settings.frigate_url,
        )

    async def stop(self) -> None:
        """Gracefully shut down all components."""
        if self.coordinator:
            await self.coordinator.stop()

        if self.mqtt_publisher:
            try:
                await self.mqtt_publisher.publish_availability(online=False)
                await self.mqtt_publisher.disconnect()
            except Exception:
                pass

        if self.frame_source:
            await self.frame_source.close()

        self.logger.info("shutdown_complete")


# ---------------------------------------------------------------------------
# Dependency helpers
# ---------------------------------------------------------------------------

_app_state: AppState | None = None


def get_state() -> AppState:
    """FastAPI dependency that provides the shared AppState."""
    assert _app_state is not None, "AppState not initialised"
    return _app_state


# ---------------------------------------------------------------------------
# Lifespan
# ---------------------------------------------------------------------------


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    """Manage startup and shutdown of background services."""
    global _app_state  # noqa: PLW0603

    settings = Settings.from_addon_options()
    setup_logging(settings.log_level)
    logger = get_logger("app.main")
    logger.info("configuration_loaded", version=settings.version)

    _app_state = AppState(settings)
    await _app_state.start()

    yield

    await _app_state.stop()
    _app_state = None
    logger.info("shutdown_complete")


# ---------------------------------------------------------------------------
# FastAPI application
# ---------------------------------------------------------------------------

app = FastAPI(
    title="Fall Detector API",
    description="AI-powered elderly fall detection for Home Assistant",
    version="0.1.0",
    lifespan=lifespan,
)


# -- Health & status --------------------------------------------------------


@app.get("/health", response_model=HealthResponse, tags=["health"])
async def health(state: AppState = Depends(get_state)) -> HealthResponse:
    """Lightweight health check consumed by the HA watchdog."""
    return HealthResponse(
        status="ok",
        version=state.settings.version,
        uptime_seconds=round(state.uptime, 1),
        cameras_monitored=len(state.cameras),
        cameras_online=sum(
            1 for c in state.cameras.values() if c.monitoring_active
        ),
    )


@app.get("/status", response_model=SystemStatus, tags=["status"])
async def status(state: AppState = Depends(get_state)) -> SystemStatus:
    """Detailed system status including per-camera state."""
    return SystemStatus(
        online=True,
        version=state.settings.version,
        uptime_seconds=round(state.uptime, 1),
        cameras=state.cameras,
        active_alerts=state.active_alerts,
        total_events=state.total_events,
        last_event=state.last_event,
        notifications_muted=state.notifications_muted,
    )


# -- Events -----------------------------------------------------------------


@app.get(
    "/events/recent",
    response_model=list[FallDetectionEvent],
    tags=["events"],
)
async def recent_events(
    state: AppState = Depends(get_state),
) -> list[FallDetectionEvent]:
    """Return the most recent fall detection events (up to 50)."""
    return list(state.recent_events)


# -- Configuration ----------------------------------------------------------


@app.post("/config/validate", tags=["config"])
async def validate_config(state: AppState = Depends(get_state)) -> JSONResponse:
    """Re-read and validate the current add-on configuration."""
    try:
        new_settings = Settings.from_addon_options()
        return JSONResponse(
            content={
                "valid": True,
                "cameras": new_settings.monitored_cameras,
                "pose_backend": new_settings.pose_backend,
                "confidence": new_settings.detection_confidence_threshold,
            }
        )
    except Exception as exc:
        return JSONResponse(
            status_code=422,
            content={"valid": False, "error": str(exc)},
        )


# -- Alerts -----------------------------------------------------------------


@app.post("/alert/test", tags=["alerts"])
async def test_alert(
    camera: str = "test_camera",
    state: AppState = Depends(get_state),
) -> FallDetectionEvent:
    """Fire a synthetic fall alert for testing notifications."""
    if state.coordinator and camera in state.cameras:
        return await state.coordinator.create_test_alert(camera)

    # Fallback for cameras not in coordinator
    event = FallDetectionEvent(
        camera=camera,
        confidence=0.95,
        stage=DetectionStage.CONFIRMED_FALL,
        person_detected=True,
        pose_summary=PoseSummary(
            torso_angle=75.0,
            is_upright=False,
            is_prone=True,
            pose_confidence=0.92,
        ),
        motion_summary=MotionSummary(
            centroid_velocity=180.0,
            vertical_displacement=0.6,
            direction="down",
            is_rapid_descent=True,
        ),
        reason_codes=[ReasonCode.RAPID_DESCENT, ReasonCode.PRONE_DWELL],
    )
    state.logger.warning("test_alert_fired", camera=camera, event_id=event.event_id)
    return event


@app.post("/alert/{action}", tags=["alerts"])
async def alert_action(
    action: AlertAction,
    camera: str | None = None,
    state: AppState = Depends(get_state),
) -> JSONResponse:
    """Perform an action on active alerts."""
    if action == AlertAction.ACKNOWLEDGE:
        if camera is None:
            raise HTTPException(400, "camera query parameter required for acknowledge")
        if state.coordinator:
            state.coordinator.acknowledge_alert(camera)
        state.logger.info("alert_acknowledged", camera=camera)
        return JSONResponse(content={"result": "acknowledged", "camera": camera})

    if action == AlertAction.MUTE:
        state.notifications_muted = True
        if state.alert_manager:
            state.alert_manager.mute()
        state.logger.info("notifications_muted")
        return JSONResponse(content={"result": "muted"})

    if action == AlertAction.UNMUTE:
        state.notifications_muted = False
        if state.alert_manager:
            state.alert_manager.unmute()
        state.logger.info("notifications_unmuted")
        return JSONResponse(content={"result": "unmuted"})

    if action == AlertAction.RESET:
        if state.coordinator:
            state.coordinator.reset_all()
        if state.alert_manager:
            state.alert_manager.reset()
        state.logger.info("alerts_reset")
        return JSONResponse(content={"result": "all_alerts_reset"})

    raise HTTPException(400, f"Unknown action: {action}")


# -- Camera -----------------------------------------------------------------


@app.get(
    "/camera/{camera_name}/state",
    response_model=CameraState,
    tags=["cameras"],
)
async def camera_state(
    camera_name: str,
    state: AppState = Depends(get_state),
) -> CameraState:
    """Return runtime state for a specific camera."""
    return state.get_camera(camera_name)


@app.get("/camera/{camera_name}/snapshot-debug", tags=["cameras"])
async def camera_snapshot_debug(
    camera_name: str,
    state: AppState = Depends(get_state),
) -> Response:
    """Return the last debug frame for a camera (if retained).

    Debug frames are JPEG images with pose keypoints and bounding boxes
    overlaid.  They are only stored when ``retain_debug_frames`` is enabled
    in the add-on configuration.
    """
    _ = state.get_camera(camera_name)  # validate camera exists

    if not state.settings.retain_debug_frames:
        raise HTTPException(
            status_code=404,
            detail="Debug frame retention is disabled in configuration",
        )

    import os
    from pathlib import Path

    debug_dir = Path(state.settings.fall_detector_data_path) / "debug_frames"
    frame_path = debug_dir / f"{camera_name}_latest.jpg"

    if not frame_path.is_file():
        raise HTTPException(
            status_code=404,
            detail=f"No debug frame available for camera '{camera_name}'",
        )

    frame_bytes = frame_path.read_bytes()
    return Response(
        content=frame_bytes,
        media_type="image/jpeg",
        headers={
            "Cache-Control": "no-cache",
            "X-Camera": camera_name,
            "X-Timestamp": datetime.utcnow().isoformat(),
        },
    )


# ---------------------------------------------------------------------------
# CLI entry-point
# ---------------------------------------------------------------------------


def main() -> None:
    """Run the Fall Detector API server."""
    settings = Settings.from_addon_options()
    setup_logging(settings.log_level)
    logger = get_logger("app.main")
    logger.info("starting_server", host="0.0.0.0", port=8099)

    uvicorn.run(
        "app.main:app",
        host="0.0.0.0",
        port=8099,
        log_level=settings.log_level,
        access_log=settings.log_level == "debug",
    )


if __name__ == "__main__":
    main()
