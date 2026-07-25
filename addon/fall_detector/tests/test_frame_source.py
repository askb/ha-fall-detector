"""Tests for frame source implementations."""
# SPDX-License-Identifier: Apache-2.0

import numpy as np
import pytest
import respx
from httpx import Response

from app.inference.frame_source import (
    FrigateFrameSource,
    HomeAssistantFrameSource,
    RtspFrameSource,
)


def _jpeg_bytes() -> bytes:
    import cv2

    frame = np.full((120, 160, 3), 128, np.uint8)
    ok, buf = cv2.imencode(".jpg", frame)
    assert ok
    return buf.tobytes()


@pytest.fixture
def test_video(tmp_path):
    """Create a short synthetic video file."""
    import cv2

    path = str(tmp_path / "test.mp4")
    writer = cv2.VideoWriter(path, cv2.VideoWriter_fourcc(*"mp4v"), 5, (160, 120))
    for i in range(20):
        frame = np.full((120, 160, 3), 128, np.uint8)
        cv2.rectangle(frame, (50, 10 + i), (70, 60 + i), (255, 255, 255), -1)
        writer.write(frame)
    writer.release()
    return path


class TestRtspFrameSource:
    @pytest.mark.asyncio
    async def test_reads_frames_from_video_file(self, test_video):
        source = RtspFrameSource(streams={"cam": test_video})
        frame, _ts = await source.get_frame("cam")
        assert frame is not None
        assert frame.shape == (120, 160, 3)
        await source.close()

    @pytest.mark.asyncio
    async def test_unknown_camera_returns_none(self):
        source = RtspFrameSource(streams={})
        frame, _ = await source.get_frame("nope")
        assert frame is None
        assert not await source.is_available("nope")

    @pytest.mark.asyncio
    async def test_is_available_for_configured_stream(self, test_video):
        source = RtspFrameSource(streams={"cam": test_video})
        assert await source.is_available("cam")
        await source.close()


class TestHomeAssistantFrameSource:
    @pytest.mark.asyncio
    @respx.mock
    async def test_fetches_frame_via_camera_proxy(self):
        respx.get("http://ha.local/api/camera_proxy/camera.living_room").mock(
            return_value=Response(200, content=_jpeg_bytes())
        )
        source = HomeAssistantFrameSource(ha_url="http://ha.local", token="t")
        frame, _ = await source.get_frame("camera.living_room")
        assert frame is not None
        assert frame.shape == (120, 160, 3)
        await source.close()

    @pytest.mark.asyncio
    @respx.mock
    async def test_prefixes_bare_entity_names(self):
        route = respx.get("http://ha.local/api/camera_proxy/camera.kitchen").mock(
            return_value=Response(200, content=_jpeg_bytes())
        )
        source = HomeAssistantFrameSource(ha_url="http://ha.local", token="t")
        frame, _ = await source.get_frame("kitchen")
        assert route.called
        assert frame is not None
        await source.close()

    @pytest.mark.asyncio
    @respx.mock
    async def test_http_error_returns_none(self):
        respx.get("http://ha.local/api/camera_proxy/camera.down").mock(return_value=Response(502))
        source = HomeAssistantFrameSource(ha_url="http://ha.local", token="t")
        frame, _ = await source.get_frame("camera.down")
        assert frame is None
        await source.close()

    @pytest.mark.asyncio
    @respx.mock
    async def test_sends_bearer_token(self):
        route = respx.get("http://ha.local/api/states/camera.cam").mock(
            return_value=Response(200, json={"state": "idle"})
        )
        source = HomeAssistantFrameSource(ha_url="http://ha.local", token="secret")
        assert await source.is_available("camera.cam")
        auth = route.calls[0].request.headers["authorization"]
        assert auth == "Bearer secret"
        await source.close()


class TestFrigateFrameSource:
    @pytest.mark.asyncio
    @respx.mock
    async def test_fetches_latest_snapshot(self):
        respx.get("http://frigate:5000/api/cam/latest.jpg").mock(return_value=Response(200, content=_jpeg_bytes()))
        source = FrigateFrameSource(frigate_url="http://frigate:5000")
        frame, _ = await source.get_frame("cam")
        assert frame is not None
        await source.close()
