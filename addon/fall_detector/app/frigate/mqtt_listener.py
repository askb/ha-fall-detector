"""MQTT listener for Frigate person detection events."""
# SPDX-License-Identifier: Apache-2.0

from __future__ import annotations

import asyncio
import json
from datetime import datetime
from typing import Any, Callable, Coroutine

import aiomqtt

from app.utils.logging import get_logger

logger = get_logger(__name__)


class FrigateEventData:
    """Parsed Frigate MQTT event."""

    def __init__(self, raw: dict[str, Any]):
        self.raw = raw
        self.event_type: str = raw.get("type", "")  # "new", "update", "end"
        after = raw.get("after", {})
        before = raw.get("before", {})
        self.event_id: str = after.get("id", "")
        self.camera: str = after.get("camera", "")
        self.label: str = after.get("label", "")
        self.top_score: float = after.get("top_score", 0.0)
        self.current_zones: list[str] = after.get("current_zones", [])
        self.has_snapshot: bool = after.get("has_snapshot", False)
        self.has_clip: bool = after.get("has_clip", False)
        self.start_time: float = after.get("start_time", 0.0)
        self.end_time: float | None = after.get("end_time")
        self.stationary: bool = after.get("stationary", False)

    @property
    def is_person(self) -> bool:
        return self.label == "person"

    @property
    def is_new(self) -> bool:
        return self.event_type == "new"

    @property
    def is_end(self) -> bool:
        return self.event_type == "end"

    @property
    def is_active(self) -> bool:
        return self.end_time is None


EventCallback = Callable[[FrigateEventData], Coroutine[Any, Any, None]]


class FrigateMqttListener:
    """Listens for Frigate events via MQTT."""

    def __init__(
        self,
        host: str,
        port: int = 1883,
        username: str | None = None,
        password: str | None = None,
        monitored_cameras: list[str] | None = None,
    ):
        self._host = host
        self._port = port
        self._username = username
        self._password = password
        self._monitored_cameras = set(monitored_cameras or [])
        self._callbacks: list[EventCallback] = []
        self._running = False
        self._task: asyncio.Task | None = None
        self._reconnect_delay = 5.0
        self._max_reconnect_delay = 60.0

    def on_person_event(self, callback: EventCallback) -> None:
        """Register a callback for person detection events."""
        self._callbacks.append(callback)

    async def start(self) -> None:
        """Start listening for MQTT messages."""
        if self._running:
            return
        self._running = True
        self._task = asyncio.create_task(self._listen_loop(), name="mqtt_listener")
        logger.info("mqtt_listener_started", host=self._host, port=self._port)

    async def stop(self) -> None:
        """Stop the MQTT listener."""
        self._running = False
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
        logger.info("mqtt_listener_stopped")

    async def _listen_loop(self) -> None:
        """Main MQTT listen loop with reconnection logic."""
        delay = self._reconnect_delay

        while self._running:
            try:
                async with aiomqtt.Client(
                    hostname=self._host,
                    port=self._port,
                    username=self._username if self._username else None,
                    password=self._password if self._password else None,
                ) as client:
                    await client.subscribe("frigate/events")
                    logger.info("mqtt_subscribed", topic="frigate/events")
                    delay = self._reconnect_delay  # Reset on successful connect

                    async for message in client.messages:
                        try:
                            payload = json.loads(message.payload.decode())
                            event = FrigateEventData(payload)

                            # Filter: only person events on monitored cameras
                            if not event.is_person:
                                continue
                            if self._monitored_cameras and event.camera not in self._monitored_cameras:
                                continue

                            logger.debug(
                                "frigate_person_event",
                                camera=event.camera,
                                type=event.event_type,
                                score=event.top_score,
                                event_id=event.event_id,
                            )

                            for callback in self._callbacks:
                                try:
                                    await callback(event)
                                except Exception:
                                    logger.exception("mqtt_callback_error")

                        except json.JSONDecodeError:
                            logger.warning("mqtt_invalid_json", topic=str(message.topic))
                        except Exception:
                            logger.exception("mqtt_message_processing_error")

            except asyncio.CancelledError:
                break
            except Exception:
                if self._running:
                    logger.warning("mqtt_connection_lost", reconnect_in=delay)
                    await asyncio.sleep(delay)
                    delay = min(delay * 2, self._max_reconnect_delay)
