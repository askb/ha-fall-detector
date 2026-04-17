"""Frigate NVR HTTP API client."""
# SPDX-License-Identifier: Apache-2.0

from __future__ import annotations

from typing import Any

import httpx

from app.utils.logging import get_logger

logger = get_logger(__name__)


class FrigateClient:
    """Client for Frigate's HTTP API."""

    def __init__(self, base_url: str, timeout: float = 10.0):
        self._base_url = base_url.rstrip("/")
        self._timeout = timeout
        self._client: httpx.AsyncClient | None = None

    async def _ensure_client(self) -> httpx.AsyncClient:
        if self._client is None or self._client.is_closed:
            self._client = httpx.AsyncClient(
                base_url=self._base_url,
                timeout=self._timeout,
            )
        return self._client

    async def get_config(self) -> dict[str, Any]:
        """Get Frigate configuration."""
        client = await self._ensure_client()
        response = await client.get("/api/config")
        response.raise_for_status()
        return response.json()

    async def get_cameras(self) -> list[str]:
        """Get list of configured camera names."""
        try:
            config = await self.get_config()
            cameras = list(config.get("cameras", {}).keys())
            logger.info("frigate_cameras_discovered", count=len(cameras), cameras=cameras)
            return cameras
        except Exception:
            logger.exception("frigate_camera_discovery_failed")
            return []

    async def get_camera_snapshot(self, camera_name: str, height: int = 480) -> bytes | None:
        """Get latest snapshot for a camera."""
        try:
            client = await self._ensure_client()
            response = await client.get(
                f"/api/{camera_name}/latest.jpg",
                params={"h": height},
            )
            if response.status_code == 200:
                return response.content
            logger.warning("snapshot_failed", camera=camera_name, status=response.status_code)
            return None
        except Exception:
            logger.exception("snapshot_error", camera=camera_name)
            return None

    async def get_events(
        self,
        camera: str | None = None,
        label: str = "person",
        limit: int = 10,
        after: float | None = None,
    ) -> list[dict[str, Any]]:
        """Get recent events from Frigate."""
        try:
            client = await self._ensure_client()
            params: dict[str, Any] = {"label": label, "limit": limit}
            if camera:
                params["camera"] = camera
            if after:
                params["after"] = after

            response = await client.get("/api/events", params=params)
            response.raise_for_status()
            return response.json()
        except Exception:
            logger.exception("events_fetch_failed")
            return []

    async def get_event_snapshot(self, event_id: str) -> bytes | None:
        """Get snapshot for a specific event."""
        try:
            client = await self._ensure_client()
            response = await client.get(f"/api/events/{event_id}/snapshot.jpg")
            if response.status_code == 200:
                return response.content
            return None
        except Exception:
            logger.exception("event_snapshot_error", event_id=event_id)
            return None

    async def get_event_clip(self, event_id: str) -> bytes | None:
        """Get clip for a specific event."""
        try:
            client = await self._ensure_client()
            response = await client.get(f"/api/events/{event_id}/clip.mp4")
            if response.status_code == 200:
                return response.content
            return None
        except Exception:
            logger.exception("event_clip_error", event_id=event_id)
            return None

    async def is_available(self) -> bool:
        """Check if Frigate is reachable."""
        try:
            client = await self._ensure_client()
            response = await client.get("/api/version")
            return response.status_code == 200
        except Exception:
            return False

    async def get_version(self) -> str | None:
        """Get Frigate version."""
        try:
            client = await self._ensure_client()
            response = await client.get("/api/version")
            if response.status_code == 200:
                return response.text.strip()
            return None
        except Exception:
            return None

    async def close(self) -> None:
        """Close the HTTP client."""
        if self._client and not self._client.is_closed:
            await self._client.aclose()
