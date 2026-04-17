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

from app.config.settings import Settings
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
        self.cameras: dict[str, CameraState] = {}
        self.recent_events: deque[FallDetectionEvent] = deque(
            maxlen=MAX_RECENT_EVENTS
        )
        self.total_events: int = 0
        self.notifications_muted: bool = False
        self._monitoring_tasks: list[asyncio.Task] = []  # type: ignore[type-arg]
        self._shutdown_event = asyncio.Event()
        self.logger = get_logger("app.state")

    # -- helpers -------------------------------------------------------------

    @property
    def uptime(self) -> float:
        return time.monotonic() - self.start_time

    @property
    def active_alerts(self) -> int:
        return sum(
            1
            for cam in self.cameras.values()
            if cam.active_alert and not cam.alert_acknowledged
        )

    @property
    def last_event(self) -> FallDetectionEvent | None:
        return self.recent_events[-1] if self.recent_events else None

    def get_camera(self, name: str) -> CameraState:
        if name not in self.cameras:
            raise HTTPException(status_code=404, detail=f"Camera '{name}' not found")
        return self.cameras[name]

    # -- lifecycle -----------------------------------------------------------

    async def start(self) -> None:
        """Initialise camera states and start background monitoring tasks."""
        for cam_name in self.settings.monitored_cameras:
            self.cameras[cam_name] = CameraState(camera_name=cam_name)
            self.logger.info("camera_registered", camera=cam_name)

        self._monitoring_tasks.append(
            asyncio.create_task(self._camera_monitor_loop())
        )
        self.logger.info(
            "monitoring_started",
            cameras=len(self.cameras),
            sample_rate=self.settings.frame_sample_rate,
        )

    async def stop(self) -> None:
        """Gracefully cancel background tasks."""
        self._shutdown_event.set()
        for task in self._monitoring_tasks:
            task.cancel()
        await asyncio.gather(*self._monitoring_tasks, return_exceptions=True)
        self._monitoring_tasks.clear()
        self.logger.info("monitoring_stopped")

    # -- background tasks ----------------------------------------------------

    async def _camera_monitor_loop(self) -> None:
        """Placeholder monitoring loop.

        The full implementation will subscribe to Frigate MQTT events,
        pull snapshots, run pose estimation, and feed the detection
        state-machine.  This skeleton keeps the add-on responsive while
        those subsystems are built out in subsequent modules.
        """
        interval = 1.0 / max(self.settings.frame_sample_rate, 0.1)
        while not self._shutdown_event.is_set():
            for cam_name, cam_state in self.cameras.items():
                if not cam_state.monitoring_active:
                    continue
                cam_state.frame_count += 1

                # Cooldown expiry check
                if (
                    cam_state.cooldown_until
                    and datetime.utcnow() >= cam_state.cooldown_until
                ):
                    cam_state.cooldown_until = None
                    self.logger.debug("cooldown_expired", camera=cam_name)

            try:
                await asyncio.wait_for(
                    self._shutdown_event.wait(), timeout=interval
                )
                break
            except asyncio.TimeoutError:
                continue

    # -- event recording -----------------------------------------------------

    def record_event(self, event: FallDetectionEvent) -> None:
        """Persist an event to the recent-events ring buffer."""
        self.recent_events.append(event)
        self.total_events += 1

        cam = self.cameras.get(event.camera)
        if cam is not None:
            cam.last_fall_event = event
            if event.stage == DetectionStage.CONFIRMED_FALL:
                cam.active_alert = True
                cam.alert_acknowledged = False
                cam.last_alert_time = event.timestamp
                cam.cooldown_until = event.timestamp + timedelta(
                    seconds=self.settings.alert_cooldown_seconds
                )
        self.logger.info(
            "event_recorded",
            event_id=event.event_id,
            camera=event.camera,
            stage=event.stage,
        )


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

    # If the camera exists in state, record against it
    if camera in state.cameras:
        state.record_event(event)
    else:
        state.recent_events.append(event)
        state.total_events += 1

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
        cam = state.get_camera(camera)
        cam.alert_acknowledged = True
        state.logger.info("alert_acknowledged", camera=camera)
        return JSONResponse(content={"result": "acknowledged", "camera": camera})

    if action == AlertAction.MUTE:
        state.notifications_muted = True
        state.logger.info("notifications_muted")
        return JSONResponse(content={"result": "muted"})

    if action == AlertAction.UNMUTE:
        state.notifications_muted = False
        state.logger.info("notifications_unmuted")
        return JSONResponse(content={"result": "unmuted"})

    if action == AlertAction.RESET:
        for cam in state.cameras.values():
            cam.active_alert = False
            cam.alert_acknowledged = False
            cam.consecutive_fall_frames = 0
            cam.fall_candidate_start = None
            cam.cooldown_until = None
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
