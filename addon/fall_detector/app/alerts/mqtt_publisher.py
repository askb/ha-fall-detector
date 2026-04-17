"""MQTT publisher for broadcasting fall detection events to Home Assistant."""
# SPDX-License-Identifier: Apache-2.0

from __future__ import annotations

import json
from datetime import datetime
from typing import Any

import aiomqtt

from app.models import FallDetectionEvent
from app.utils.logging import get_logger

logger = get_logger(__name__)

TOPIC_PREFIX = "fall_detector"


class MqttPublisher:
    """Publishes fall detection events and state via MQTT."""

    def __init__(
        self,
        host: str,
        port: int = 1883,
        username: str | None = None,
        password: str | None = None,
    ):
        self._host = host
        self._port = port
        self._username = username
        self._password = password
        self._client: aiomqtt.Client | None = None

    async def connect(self) -> None:
        """Establish MQTT connection."""
        try:
            self._client = aiomqtt.Client(
                hostname=self._host,
                port=self._port,
                username=self._username if self._username else None,
                password=self._password if self._password else None,
            )
            await self._client.__aenter__()
            logger.info("mqtt_publisher_connected", host=self._host)
        except Exception:
            logger.exception("mqtt_publisher_connect_failed")
            self._client = None

    async def disconnect(self) -> None:
        """Close MQTT connection."""
        if self._client:
            try:
                await self._client.__aexit__(None, None, None)
            except Exception:
                pass
            self._client = None

    async def publish_fall_event(self, event: FallDetectionEvent) -> None:
        """Publish a fall detection event."""
        if not self._client:
            logger.warning("mqtt_not_connected_for_publish")
            return

        topic = f"{TOPIC_PREFIX}/{event.camera}/fall"
        payload = {
            "event_id": event.event_id,
            "camera": event.camera,
            "timestamp": event.timestamp.isoformat(),
            "confidence": event.confidence,
            "stage": event.stage.value,
            "person_detected": event.person_detected,
            "recovery_detected": event.recovery_detected,
            "reason_codes": [r.value for r in event.reason_codes],
            "frigate_event_id": event.frigate_event_id,
            "snapshot_url": event.snapshot_url,
        }

        try:
            await self._client.publish(topic, json.dumps(payload), qos=1, retain=True)
            logger.debug("mqtt_event_published", topic=topic, event_id=event.event_id)
        except Exception:
            logger.exception("mqtt_publish_error", topic=topic)

    async def publish_camera_state(self, camera_name: str, state: dict[str, Any]) -> None:
        """Publish camera monitoring state."""
        if not self._client:
            return
        topic = f"{TOPIC_PREFIX}/{camera_name}/state"
        try:
            await self._client.publish(topic, json.dumps(state), qos=1, retain=True)
        except Exception:
            logger.exception("mqtt_state_publish_error", camera=camera_name)

    async def publish_system_status(self, status: dict[str, Any]) -> None:
        """Publish overall system status."""
        if not self._client:
            return
        topic = f"{TOPIC_PREFIX}/status"
        try:
            await self._client.publish(topic, json.dumps(status), qos=1, retain=True)
        except Exception:
            logger.exception("mqtt_status_publish_error")

    async def publish_availability(self, online: bool) -> None:
        """Publish availability state."""
        if not self._client:
            return
        topic = f"{TOPIC_PREFIX}/availability"
        payload = "online" if online else "offline"
        try:
            await self._client.publish(topic, payload, qos=1, retain=True)
        except Exception:
            logger.exception("mqtt_availability_publish_error")

    async def notify_alert(self, event: FallDetectionEvent, escalation_level: int = 0) -> None:
        """Publish alert notification for HA consumption."""
        await self.publish_fall_event(event)

        # Also publish to a dedicated alerts topic for easy automation
        if not self._client:
            return

        topic = f"{TOPIC_PREFIX}/alerts"
        payload = {
            "camera": event.camera,
            "confidence": event.confidence,
            "timestamp": event.timestamp.isoformat(),
            "escalation_level": escalation_level,
            "event_id": event.event_id,
            "message": (
                f"⚠️ Fall detected on {event.camera} "
                f"(confidence: {event.confidence:.0%}, "
                f"escalation: {escalation_level})"
            ),
        }

        try:
            await self._client.publish(topic, json.dumps(payload), qos=1)
            logger.info(
                "alert_notification_published",
                camera=event.camera,
                escalation=escalation_level,
            )
        except Exception:
            logger.exception("alert_publish_error")
