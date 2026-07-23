"""Frame source abstraction for camera feeds."""
# SPDX-License-Identifier: Apache-2.0

from __future__ import annotations

import abc
import contextlib
from datetime import datetime

import httpx
import numpy as np

from app.utils.logging import get_logger

logger = get_logger(__name__)


class FrameSource(abc.ABC):
    """Abstract interface for obtaining video frames."""

    @abc.abstractmethod
    async def get_frame(self, camera_name: str) -> tuple[np.ndarray | None, datetime]:
        """Get the latest frame for a camera. Returns (frame, timestamp)."""

    @abc.abstractmethod
    async def is_available(self, camera_name: str) -> bool:
        """Check if camera feed is available."""


class FrigateFrameSource(FrameSource):
    """Obtain frames from Frigate's snapshot API."""

    def __init__(self, frigate_url: str, timeout: float = 10.0):
        self._frigate_url = frigate_url.rstrip("/")
        self._timeout = timeout
        self._client: httpx.AsyncClient | None = None

    async def _ensure_client(self) -> httpx.AsyncClient:
        if self._client is None or self._client.is_closed:
            self._client = httpx.AsyncClient(timeout=self._timeout)
        return self._client

    async def get_frame(self, camera_name: str) -> tuple[np.ndarray | None, datetime]:
        """Get latest frame from Frigate snapshot endpoint."""
        import cv2

        try:
            client = await self._ensure_client()
            url = f"{self._frigate_url}/api/{camera_name}/latest.jpg"
            response = await client.get(url, params={"h": 480})

            if response.status_code != 200:
                logger.warning("frame_fetch_failed", camera=camera_name, status=response.status_code)
                return None, datetime.utcnow()

            # Decode JPEG to numpy array
            img_array = np.frombuffer(response.content, dtype=np.uint8)
            frame = cv2.imdecode(img_array, cv2.IMREAD_COLOR)

            if frame is None:
                logger.warning("frame_decode_failed", camera=camera_name)
                return None, datetime.utcnow()

            return frame, datetime.utcnow()

        except Exception:
            logger.exception("frame_source_error", camera=camera_name)
            return None, datetime.utcnow()

    async def is_available(self, camera_name: str) -> bool:
        """Check if Frigate camera is accessible."""
        try:
            client = await self._ensure_client()
            response = await client.get(f"{self._frigate_url}/api/{camera_name}")
            return response.status_code == 200
        except Exception:
            return False

    async def close(self) -> None:
        """Close the HTTP client."""
        if self._client and not self._client.is_closed:
            await self._client.aclose()


class HomeAssistantFrameSource(FrameSource):
    """Obtain frames from any HA camera entity via the camera-proxy API.

    Works with every camera integrated in Home Assistant (ONVIF, RTSP,
    generic, Ring, Eufy, ESPHome, ...) — no Frigate required.  Camera names
    are entity IDs, e.g. ``camera.living_room``.
    """

    def __init__(
        self,
        ha_url: str = "http://supervisor/core",
        token: str | None = None,
        timeout: float = 10.0,
    ):
        import os

        self._ha_url = ha_url.rstrip("/")
        self._token = token or os.environ.get("SUPERVISOR_TOKEN", "")
        self._timeout = timeout
        self._client: httpx.AsyncClient | None = None

    async def _ensure_client(self) -> httpx.AsyncClient:
        if self._client is None or self._client.is_closed:
            self._client = httpx.AsyncClient(
                timeout=self._timeout,
                headers={"Authorization": f"Bearer {self._token}"},
            )
        return self._client

    def _entity_id(self, camera_name: str) -> str:
        return camera_name if camera_name.startswith("camera.") else f"camera.{camera_name}"

    async def get_frame(self, camera_name: str) -> tuple[np.ndarray | None, datetime]:
        import cv2

        try:
            client = await self._ensure_client()
            url = f"{self._ha_url}/api/camera_proxy/{self._entity_id(camera_name)}"
            response = await client.get(url)
            if response.status_code != 200:
                logger.warning("frame_fetch_failed", camera=camera_name, status=response.status_code)
                return None, datetime.utcnow()

            img_array = np.frombuffer(response.content, dtype=np.uint8)
            frame = cv2.imdecode(img_array, cv2.IMREAD_COLOR)
            if frame is None:
                logger.warning("frame_decode_failed", camera=camera_name)
                return None, datetime.utcnow()
            return frame, datetime.utcnow()
        except Exception:
            logger.exception("frame_source_error", camera=camera_name)
            return None, datetime.utcnow()

    async def is_available(self, camera_name: str) -> bool:
        try:
            client = await self._ensure_client()
            url = f"{self._ha_url}/api/states/{self._entity_id(camera_name)}"
            response = await client.get(url)
            return response.status_code == 200
        except Exception:
            return False

    async def close(self) -> None:
        if self._client and not self._client.is_closed:
            await self._client.aclose()


class RtspFrameSource(FrameSource):
    """Obtain frames directly from RTSP/HTTP/video-file URLs via OpenCV.

    For local testing with any webcam or RTSP camera without HA or Frigate.
    Streams are configured as ``name|url`` pairs.
    """

    def __init__(self, streams: dict[str, str]):
        self._streams = streams
        self._captures: dict = {}

    def _read_frame(self, camera_name: str) -> np.ndarray | None:
        """Blocking read; runs in a thread executor."""
        import cv2

        url = self._streams.get(camera_name)
        if url is None:
            return None

        cap = self._captures.get(camera_name)
        if cap is None or not cap.isOpened():
            cap = cv2.VideoCapture(int(url) if url.isdigit() else url)
            cap.set(cv2.CAP_PROP_BUFFERSIZE, 1)
            self._captures[camera_name] = cap

        # ponytail: grab a few frames to drain stale buffer at low sample
        # rates; a reader thread per camera if drift ever matters
        for _ in range(2):
            cap.grab()
        ok, frame = cap.read()
        if not ok:
            cap.release()
            self._captures.pop(camera_name, None)
            return None
        return frame

    async def get_frame(self, camera_name: str) -> tuple[np.ndarray | None, datetime]:
        import asyncio

        try:
            frame = await asyncio.get_running_loop().run_in_executor(None, self._read_frame, camera_name)
            if frame is None:
                logger.warning("frame_fetch_failed", camera=camera_name)
            return frame, datetime.utcnow()
        except Exception:
            logger.exception("frame_source_error", camera=camera_name)
            return None, datetime.utcnow()

    async def is_available(self, camera_name: str) -> bool:
        return camera_name in self._streams

    async def close(self) -> None:
        for cap in self._captures.values():
            with contextlib.suppress(Exception):
                cap.release()
        self._captures.clear()
