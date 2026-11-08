# SPDX-License-Identifier: Apache-2.0
# SPDX-FileCopyrightText: 2026 The Linux Foundation
"""Corroborate camera fall detections with Home Assistant sensor entities.

A camera fall can be cross-checked against another sensor in the same room,
typically an mmWave radar fall sensor (Seeed MR60FDA2, Aqara FP2) exposed
as a ``binary_sensor`` in Home Assistant.
"""

from __future__ import annotations

import os
from datetime import UTC, datetime

import httpx

from app.utils.logging import get_logger

logger = get_logger(__name__)

ACTIVE_STATES = frozenset({"on", "true", "detected", "fall", "fallen", "fall_detected"})


class SensorFusion:
    """Query HA entity state to confirm or refute a camera fall."""

    def __init__(
        self,
        sensors: dict[str, str],
        window_seconds: int = 60,
        ha_url: str = "http://supervisor/core",
        token: str | None = None,
        timeout: float = 3.0,
    ):
        self._sensors = sensors
        self._window_seconds = window_seconds
        self._ha_url = ha_url.rstrip("/")
        self._token = token or os.environ.get("SUPERVISOR_TOKEN", "")
        self._timeout = timeout
        self._client: httpx.AsyncClient | None = None

    def has_sensor(self, camera_name: str) -> bool:
        return camera_name in self._sensors

    async def _ensure_client(self) -> httpx.AsyncClient:
        if self._client is None or self._client.is_closed:
            self._client = httpx.AsyncClient(
                timeout=self._timeout,
                headers={"Authorization": f"Bearer {self._token}"} if self._token else {},
            )
        return self._client

    async def corroborate(self, camera_name: str) -> bool | None:
        """Return True if the linked sensor agrees, False if not, None if unknown.

        A sensor agrees when it is currently active, or when it changed state
        within the window (radar fall sensors often pulse briefly).
        """
        entity_id = self._sensors.get(camera_name)
        if not entity_id:
            return None
        try:
            client = await self._ensure_client()
            response = await client.get(f"{self._ha_url}/api/states/{entity_id}")
            if response.status_code != 200:
                logger.warning("fusion_sensor_unavailable", entity=entity_id, status=response.status_code)
                return None
            data = response.json()
        except Exception:
            logger.exception("fusion_sensor_error", entity=entity_id)
            return None

        state = str(data.get("state", "")).lower()
        if state in ("unavailable", "unknown", ""):
            return None
        if state in ACTIVE_STATES:
            return True

        last_changed = data.get("last_changed")
        if last_changed:
            try:
                changed = datetime.fromisoformat(last_changed)
                if changed.tzinfo is None:
                    changed = changed.replace(tzinfo=UTC)
                age = (datetime.now(UTC) - changed).total_seconds()
                return age <= self._window_seconds
            except ValueError:
                pass
        return False

    async def close(self) -> None:
        if self._client and not self._client.is_closed:
            await self._client.aclose()
