"""End-to-end pipeline smoke test.

Runs the real DetectionCoordinator against a synthetic video file with the
real MoveNet model when available.  This is the "is it actually working"
test — run it any time with:

    FD_MODEL_DIR=/path/to/models pytest tests/test_pipeline_e2e.py -v

Inside the add-on container the model is baked at /app/models, so this
runs without any setup.  Without a model it still verifies the pipeline
plumbing using the estimator's fallback path.
"""
# SPDX-License-Identifier: Apache-2.0

import asyncio
import os
from pathlib import Path

import numpy as np
import pytest

from app.config.settings import Settings
from app.inference.detection_coordinator import DetectionCoordinator
from app.inference.frame_source import RtspFrameSource
from app.inference.pose_estimator import MoveNetEstimator


def _model_dir() -> str | None:
    for candidate in (os.environ.get("FD_MODEL_DIR"), "/app/models"):
        if candidate and (Path(candidate) / "movenet_lightning.tflite").is_file():
            return candidate
    return None


@pytest.fixture
def fall_video(tmp_path):
    """Synthetic video: a bright vertical bar that tips over horizontally."""
    import cv2

    path = str(tmp_path / "fall.mp4")
    writer = cv2.VideoWriter(path, cv2.VideoWriter_fourcc(*"mp4v"), 10, (320, 240))
    for i in range(60):
        frame = np.full((240, 320, 3), 100, np.uint8)
        if i < 30:  # upright
            cv2.rectangle(frame, (140, 40), (180, 200), (255, 255, 255), -1)
        else:  # fallen
            cv2.rectangle(frame, (80, 180), (240, 220), (255, 255, 255), -1)
        writer.write(frame)
    writer.release()
    return path


@pytest.mark.asyncio
async def test_pipeline_processes_frames_end_to_end(fall_video, tmp_path):
    """The full loop (frame source -> pose -> scorer) runs without errors."""
    settings = Settings(
        camera_source="rtsp",
        rtsp_streams=[f"e2e_cam|{fall_video}"],
        monitored_cameras=["e2e_cam"],
        frame_sample_rate=10.0,
        mqtt_host="localhost",
    )
    model_dir = _model_dir() or str(tmp_path / "no-models")

    frame_source = RtspFrameSource(streams=settings.rtsp_stream_map())
    estimator = MoveNetEstimator(model_dir=model_dir)
    coordinator = DetectionCoordinator(
        settings=settings,
        frame_source=frame_source,
        pose_estimator=estimator,
    )

    events = []
    coordinator.on_event(lambda e: _collect(events, e))

    await coordinator.start()
    await asyncio.sleep(2.0)
    await coordinator.stop()
    await frame_source.close()

    state = coordinator.camera_states["e2e_cam"]
    assert state.frame_count >= 5, "pipeline did not process frames"
    assert state.error_count == 0, "frame source errored"


async def _collect(events: list, event) -> None:
    events.append(event)


@pytest.mark.asyncio
@pytest.mark.skipif(_model_dir() is None, reason="MoveNet model not available")
async def test_real_model_loads_and_infers(fall_video):
    """The real MoveNet model loads and produces pose output on real frames."""
    import cv2

    estimator = MoveNetEstimator(model_dir=_model_dir())
    await estimator.initialize()
    assert estimator.is_ready(), "model failed to load"

    cap = cv2.VideoCapture(fall_video)
    ok, frame = cap.read()
    cap.release()
    assert ok

    pose = await estimator.estimate_pose(frame)
    assert pose is not None
    assert pose.keypoints, "model returned no keypoints"
    assert len(pose.keypoints) == 17
