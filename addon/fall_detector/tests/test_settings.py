# SPDX-License-Identifier: Apache-2.0
"""Tests for camera source settings."""

from app.config.settings import Settings


def test_camera_source_default_frigate():
    assert Settings().camera_source == "frigate"


def test_rtsp_stream_map_parses_pairs():
    s = Settings(
        camera_source="rtsp",
        rtsp_streams=["cam1|rtsp://host/stream", "webcam|0", "bad_entry"],
    )
    assert s.rtsp_stream_map() == {"cam1": "rtsp://host/stream", "webcam": "0"}
