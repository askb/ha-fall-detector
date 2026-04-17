# SPDX-License-Identifier: Apache-2.0
# SPDX-FileCopyrightText: 2025 The Linux Foundation
"""Application settings loaded from Home Assistant add-on options."""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Literal

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    """Fall Detector add-on configuration.

    Values are loaded from the HA add-on options.json written by the
    Supervisor, with environment-variable overrides for local development.
    """

    # --- Frigate integration ---
    frigate_url: str = "http://ccab4aaf-frigate:5000"
    mqtt_host: str = "core-mosquitto"
    mqtt_port: int = Field(default=1883, ge=1, le=65535)
    mqtt_username: str = ""
    mqtt_password: str = ""

    # --- Camera selection ---
    monitored_cameras: list[str] = Field(default_factory=list)

    # --- Frame sampling ---
    frame_sample_rate: float = Field(default=2.0, gt=0.0, le=30.0)

    # --- Detection pipeline ---
    person_gate_required: bool = True
    pose_backend: Literal["movenet_lightning", "movenet_thunder"] = (
        "movenet_lightning"
    )
    detection_confidence_threshold: float = Field(default=0.7, ge=0.0, le=1.0)

    # --- Temporal parameters ---
    fall_confirmation_seconds: int = Field(default=5, ge=1, le=120)
    recovery_window_seconds: int = Field(default=30, ge=1, le=600)
    alert_cooldown_seconds: int = Field(default=120, ge=0, le=3600)

    # --- Media capture ---
    snapshot_on_alert: bool = True
    clip_on_alert: bool = False
    retain_debug_frames: bool = False

    # --- Logging ---
    log_level: Literal["debug", "info", "warning", "error"] = "info"

    # --- Internal paths (set by run.sh, not user-configurable) ---
    fall_detector_config_path: str = "/data/options.json"
    fall_detector_data_path: str = "/data"
    fall_detector_share_path: str = "/share/fall_detector"
    fall_detector_media_path: str = "/media/fall_detector"

    # --- Static metadata ---
    version: str = "0.1.0"

    model_config = {
        "env_prefix": "FALL_DETECTOR_",
        "extra": "ignore",
    }

    @field_validator("detection_confidence_threshold")
    @classmethod
    def _confidence_range(cls, value: float) -> float:
        if not 0.0 <= value <= 1.0:
            raise ValueError("detection_confidence_threshold must be between 0 and 1")
        return value

    @field_validator("frame_sample_rate")
    @classmethod
    def _positive_rate(cls, value: float) -> float:
        if value <= 0:
            raise ValueError("frame_sample_rate must be positive")
        return value

    @classmethod
    def from_addon_options(cls, config_path: str | None = None) -> Settings:
        """Create a Settings instance from the HA add-on options.json.

        The Supervisor writes user-configured values to ``/data/options.json``.
        This class method reads that file and merges the values with any
        environment-variable overrides.

        Args:
            config_path: Explicit path to options.json.  Falls back to the
                ``FALL_DETECTOR_CONFIG_PATH`` env var, then ``/data/options.json``.

        Returns:
            A fully validated ``Settings`` instance.
        """
        if config_path is None:
            config_path = os.environ.get(
                "FALL_DETECTOR_CONFIG_PATH", "/data/options.json"
            )

        options_file = Path(config_path)
        addon_options: dict = {}

        if options_file.is_file():
            with open(options_file, encoding="utf-8") as fh:
                addon_options = json.load(fh)

        # Normalise keys: HA options use snake_case already but let's be safe
        normalised = {
            key.lower().replace("-", "_"): value
            for key, value in addon_options.items()
        }

        return cls(**normalised)
