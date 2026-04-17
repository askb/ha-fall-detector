"""Alert management with cooldown, escalation, and notification routing."""
# SPDX-License-Identifier: Apache-2.0

from __future__ import annotations

import asyncio
from collections import defaultdict
from datetime import datetime, timedelta
from typing import Any

from app.models import FallDetectionEvent
from app.utils.logging import get_logger

logger = get_logger(__name__)


class AlertManager:
    """Manages fall detection alerts with debounce, cooldown, and escalation."""

    def __init__(
        self,
        cooldown_seconds: int = 120,
        escalation_intervals: list[int] | None = None,
    ):
        self._cooldown_seconds = cooldown_seconds
        self._escalation_intervals = escalation_intervals or [120, 300, 600]
        self._active_alerts: dict[str, FallDetectionEvent] = {}
        self._last_alert_time: dict[str, datetime] = {}
        self._acknowledged: set[str] = set()
        self._muted = False
        self._escalation_tasks: dict[str, asyncio.Task] = {}
        self._notification_callbacks: list = []

    @property
    def is_muted(self) -> bool:
        return self._muted

    @property
    def active_alert_count(self) -> int:
        return len(self._active_alerts)

    def on_notification(self, callback) -> None:
        """Register notification callback: async def callback(event, escalation_level)."""
        self._notification_callbacks.append(callback)

    async def process_alert(self, event: FallDetectionEvent) -> bool:
        """Process a confirmed fall event. Returns True if alert was sent."""
        camera = event.camera
        now = datetime.utcnow()

        # Check cooldown
        last = self._last_alert_time.get(camera)
        if last and (now - last).total_seconds() < self._cooldown_seconds:
            logger.info("alert_cooldown_active", camera=camera)
            return False

        # Check mute
        if self._muted:
            logger.info("alerts_muted", camera=camera)
            return False

        # Store alert
        self._active_alerts[camera] = event
        self._last_alert_time[camera] = now

        # Send initial notification
        await self._send_notification(event, escalation_level=0)

        # Start escalation timer
        self._start_escalation(event)

        logger.warning(
            "alert_sent",
            camera=camera,
            confidence=event.confidence,
            event_id=event.event_id,
        )
        return True

    async def _send_notification(self, event: FallDetectionEvent, escalation_level: int) -> None:
        """Send notification to all registered callbacks."""
        for callback in self._notification_callbacks:
            try:
                await callback(event, escalation_level)
            except Exception:
                logger.exception("notification_callback_error", escalation=escalation_level)

    def _start_escalation(self, event: FallDetectionEvent) -> None:
        """Start escalation timers for an alert."""
        camera = event.camera

        # Cancel existing escalation
        existing = self._escalation_tasks.get(camera)
        if existing and not existing.done():
            existing.cancel()

        task = asyncio.create_task(
            self._escalation_loop(event),
            name=f"escalation_{camera}",
        )
        self._escalation_tasks[camera] = task

    async def _escalation_loop(self, event: FallDetectionEvent) -> None:
        """Escalate alert if not acknowledged."""
        camera = event.camera

        for level, interval in enumerate(self._escalation_intervals, start=1):
            await asyncio.sleep(interval)

            # Check if still active and not acknowledged
            if camera not in self._active_alerts:
                return
            if camera in self._acknowledged:
                return
            if self._muted:
                continue

            logger.warning(
                "alert_escalation",
                camera=camera,
                level=level,
                event_id=event.event_id,
            )
            await self._send_notification(event, escalation_level=level)

    def acknowledge(self, camera: str | None = None) -> bool:
        """Acknowledge an alert, stopping escalation."""
        if camera:
            if camera in self._active_alerts:
                self._acknowledged.add(camera)
                del self._active_alerts[camera]
                task = self._escalation_tasks.pop(camera, None)
                if task and not task.done():
                    task.cancel()
                logger.info("alert_acknowledged", camera=camera)
                return True
            return False

        # Acknowledge all
        if not self._active_alerts:
            return False
        for cam in list(self._active_alerts.keys()):
            self._acknowledged.add(cam)
            task = self._escalation_tasks.pop(cam, None)
            if task and not task.done():
                task.cancel()
        self._active_alerts.clear()
        logger.info("all_alerts_acknowledged")
        return True

    def mute(self) -> None:
        """Mute all notifications."""
        self._muted = True
        logger.info("notifications_muted")

    def unmute(self) -> None:
        """Unmute notifications."""
        self._muted = False
        logger.info("notifications_unmuted")

    def reset(self, camera: str | None = None) -> None:
        """Reset alert state."""
        if camera:
            self._active_alerts.pop(camera, None)
            self._acknowledged.discard(camera)
            self._last_alert_time.pop(camera, None)
            task = self._escalation_tasks.pop(camera, None)
            if task and not task.done():
                task.cancel()
        else:
            for task in self._escalation_tasks.values():
                if not task.done():
                    task.cancel()
            self._active_alerts.clear()
            self._acknowledged.clear()
            self._last_alert_time.clear()
            self._escalation_tasks.clear()

    def get_active_alerts(self) -> dict[str, FallDetectionEvent]:
        """Get all active (unacknowledged) alerts."""
        return dict(self._active_alerts)
