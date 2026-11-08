"""Tests for HA sensor fusion corroboration."""
# SPDX-License-Identifier: Apache-2.0
# SPDX-FileCopyrightText: 2026 The Linux Foundation

from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock, MagicMock

import httpx
import pytest
import respx

from app.fusion import SensorFusion
from app.inference.detection_coordinator import DetectionCoordinator
from app.inference.fall_scorer import ScoreResult
from app.models import DetectionStage, MotionSummary, PoseSummary, ReasonCode

HA = "http://ha.test"
ENTITY = "binary_sensor.living_room_fall"


def _fusion() -> SensorFusion:
    return SensorFusion(sensors={"living_room": ENTITY}, window_seconds=60, ha_url=HA, token="t")


def _state(state: str, age_seconds: float = 3600) -> dict:
    changed = datetime.now(UTC) - timedelta(seconds=age_seconds)
    return {"entity_id": ENTITY, "state": state, "last_changed": changed.isoformat()}


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("payload", "status", "expected"),
    [
        (_state("on"), 200, True),
        (_state("off", age_seconds=10), 200, True),  # pulsed recently
        (_state("off", age_seconds=600), 200, False),
        (_state("unavailable"), 200, None),
        ({}, 404, None),
    ],
)
@respx.mock
async def test_corroborate(payload, status, expected):
    respx.get(f"{HA}/api/states/{ENTITY}").mock(return_value=httpx.Response(status, json=payload))
    fusion = _fusion()
    assert await fusion.corroborate("living_room") is expected
    await fusion.close()


@pytest.mark.asyncio
@respx.mock
async def test_corroborate_network_error_fails_open():
    respx.get(f"{HA}/api/states/{ENTITY}").mock(side_effect=httpx.ConnectError("down"))
    fusion = _fusion()
    assert await fusion.corroborate("living_room") is None
    assert await fusion.corroborate("other_camera") is None
    await fusion.close()


def test_fusion_sensor_map(settings):
    settings.fusion_sensors = ["living_room|binary_sensor.fp2_fall", "bad-entry", " hall | binary_sensor.x "]
    assert settings.fusion_sensor_map() == {
        "living_room": "binary_sensor.fp2_fall",
        "hall": "binary_sensor.x",
    }


def _coordinator(settings, mode: str, agrees: bool | None) -> tuple[DetectionCoordinator, list]:
    settings.monitored_cameras = ["living_room"]
    settings.fusion_mode = mode
    fusion = MagicMock(spec=SensorFusion)
    fusion.has_sensor.return_value = True
    fusion.corroborate = AsyncMock(return_value=agrees)
    coord = DetectionCoordinator(settings, frame_source=MagicMock(), pose_estimator=MagicMock(), fusion=fusion)
    alerts: list = []

    async def _cb(event):
        alerts.append(event)

    coord.on_alert(_cb)
    return coord, alerts


def _result() -> ScoreResult:
    return ScoreResult(
        stage=DetectionStage.CONFIRMED_FALL,
        confidence=0.8,
        reason_codes=[ReasonCode.PRONE_DWELL],
        should_alert=True,
        pose_summary=PoseSummary(),
        motion_summary=MotionSummary(),
    )


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("mode", "agrees", "alerted", "code"),
    [
        ("boost", True, True, ReasonCode.SENSOR_CONFIRMED),
        ("boost", False, True, None),
        ("require", True, True, ReasonCode.SENSOR_CONFIRMED),
        ("require", False, False, None),
        ("require", None, True, ReasonCode.SENSOR_UNAVAILABLE),
    ],
)
async def test_confirmed_fall_fusion(settings, mode, agrees, alerted, code):
    coord, alerts = _coordinator(settings, mode, agrees)
    state = coord.camera_states["living_room"]
    await coord._handle_confirmed_fall("living_room", state, _result(), datetime.utcnow())

    assert bool(alerts) is alerted
    assert state.active_alert is alerted
    if alerted:
        assert (code in alerts[0].reason_codes) if code else alerts[0].reason_codes == [ReasonCode.PRONE_DWELL]
        assert alerts[0].confidence == pytest.approx(0.9 if code == ReasonCode.SENSOR_CONFIRMED else 0.8)
    else:
        assert state.cooldown_until is None  # re-checked on the next frame


@pytest.mark.asyncio
async def test_fusion_off_skips_sensor(settings):
    coord, alerts = _coordinator(settings, "off", False)
    await coord._handle_confirmed_fall("living_room", coord.camera_states["living_room"], _result(), datetime.utcnow())
    assert len(alerts) == 1
    coord._fusion.corroborate.assert_not_called()
