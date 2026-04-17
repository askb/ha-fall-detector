"""Frame source abstraction for camera feeds."""
# SPDX-License-Identifier: Apache-2.0

from __future__ import annotations

import abc
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
