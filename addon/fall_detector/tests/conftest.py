"""Test fixtures for fall detector add-on tests."""
# SPDX-License-Identifier: Apache-2.0

import numpy as np
import pytest

from app.config.settings import Settings
from app.inference.fall_scorer import FallScorer, ScoringConfig
from app.models import CameraState


@pytest.fixture
def sample_frame() -> np.ndarray:
    """Create a synthetic test frame."""
    frame = np.zeros((480, 640, 3), dtype=np.uint8)
    # Draw a simple person-like shape (rectangle body + circle head)
    frame[100:400, 280:360] = 200  # Body
    frame[60:100, 295:345] = 200  # Head
    return frame


@pytest.fixture
def settings() -> Settings:
    """Create test settings."""
    return Settings(
        frigate_url="http://localhost:5000",
        mqtt_host="localhost",
        mqtt_port=1883,
        monitored_cameras=["test_camera", "bedroom"],
        frame_sample_rate=1.0,
        person_gate_required=True,
        pose_backend="movenet_lightning",
        detection_confidence_threshold=0.7,
        fall_confirmation_seconds=3,
        recovery_window_seconds=15,
        alert_cooldown_seconds=60,
        snapshot_on_alert=False,
        clip_on_alert=False,
        retain_debug_frames=False,
        log_level="debug",
    )


@pytest.fixture
def camera_state() -> CameraState:
    """Create a fresh camera state."""
    return CameraState(camera_name="test_camera")


@pytest.fixture
def scoring_config() -> ScoringConfig:
    """Create test scoring config."""
    return ScoringConfig(
        confidence_threshold=0.7,
        fall_confirmation_seconds=3,
        recovery_window_seconds=15,
        alert_cooldown_seconds=60,
        min_candidate_frames=2,
    )


@pytest.fixture
def fall_scorer(scoring_config: ScoringConfig) -> FallScorer:
    """Create a fall scorer with test config."""
    return FallScorer(config=scoring_config)
