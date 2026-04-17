"""API client for the Fall Detector add-on."""
# SPDX-License-Identifier: Apache-2.0

from __future__ import annotations

import logging
from typing import Any

import httpx

_LOGGER = logging.getLogger(__name__)


class FallDetectorApiError(Exception):
    """Base exception for API errors."""


class FallDetectorConnectionError(FallDetectorApiError):
    """Connection error."""


class FallDetectorApi:
    """Client for the Fall Detector add-on REST API."""

    def __init__(self, base_url: str, timeout: float = 10.0) -> None:
        """Initialize the API client."""
        self._base_url = base_url.rstrip("/")
        self._timeout = timeout
        self._client: httpx.AsyncClient | None = None

    async def _ensure_client(self) -> httpx.AsyncClient:
        """Ensure HTTP client is available."""
        if self._client is None or self._client.is_closed:
            self._client = httpx.AsyncClient(
                base_url=self._base_url,
                timeout=self._timeout,
            )
        return self._client

    async def async_get_health(self) -> dict[str, Any]:
        """Get add-on health status."""
        return await self._get("/health")

    async def async_get_status(self) -> dict[str, Any]:
        """Get full system status including camera states."""
        return await self._get("/status")

    async def async_get_recent_events(self) -> list[dict[str, Any]]:
        """Get recent detection events."""
        return await self._get("/events/recent")

    async def async_get_camera_state(self, camera_name: str) -> dict[str, Any]:
        """Get state for a specific camera."""
        return await self._get(f"/camera/{camera_name}/state")

    async def async_test_alert(self, camera_name: str) -> dict[str, Any]:
        """Trigger a test alert."""
        return await self._post("/alert/test", json={"camera": camera_name})

    async def async_acknowledge_alert(
        self, camera_name: str | None = None,
    ) -> dict[str, Any]:
        """Acknowledge an alert."""
        payload = {"camera": camera_name} if camera_name else {}
        return await self._post("/alert/acknowledge", json=payload)

    async def async_mute_notifications(self) -> dict[str, Any]:
        """Mute all notifications."""
        return await self._post("/alert/mute")

    async def async_unmute_notifications(self) -> dict[str, Any]:
        """Unmute notifications."""
        return await self._post("/alert/unmute")

    async def async_reset_camera(self, camera_name: str) -> dict[str, Any]:
        """Reset state for a camera."""
        return await self._post("/alert/reset", json={"camera": camera_name})

    async def async_reset_all(self) -> dict[str, Any]:
        """Reset all camera states."""
        return await self._post("/alert/reset")

    async def async_validate_config(self) -> dict[str, Any]:
        """Validate current configuration."""
        return await self._post("/config/validate")

    async def async_close(self) -> None:
        """Close the HTTP client."""
        if self._client and not self._client.is_closed:
            await self._client.aclose()

    async def _get(self, path: str) -> Any:
        """Perform a GET request."""
        try:
            client = await self._ensure_client()
            response = await client.get(path)
            response.raise_for_status()
            return response.json()
        except httpx.ConnectError as err:
            raise FallDetectorConnectionError(
                f"Cannot connect to Fall Detector add-on at {self._base_url}"
            ) from err
        except httpx.HTTPStatusError as err:
            raise FallDetectorApiError(
                f"API error {err.response.status_code}: {err.response.text}"
            ) from err
        except Exception as err:
            raise FallDetectorApiError(f"Unexpected error: {err}") from err

    async def _post(self, path: str, json: dict | None = None) -> Any:
        """Perform a POST request."""
        try:
            client = await self._ensure_client()
            response = await client.post(path, json=json or {})
            response.raise_for_status()
            return response.json()
        except httpx.ConnectError as err:
            raise FallDetectorConnectionError(
                f"Cannot connect to Fall Detector add-on at {self._base_url}"
            ) from err
        except httpx.HTTPStatusError as err:
            raise FallDetectorApiError(
                f"API error {err.response.status_code}: {err.response.text}"
            ) from err
        except Exception as err:
            raise FallDetectorApiError(f"Unexpected error: {err}") from err
