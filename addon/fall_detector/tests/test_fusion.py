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


def _score(stage: DetectionStage, should_alert: bool = False) -> ScoreResult:
    return ScoreResult(
        stage=stage,
        confidence=0.8 if should_alert else 0.6,
        reason_codes=[ReasonCode.PRONE_DWELL] if should_alert else [],
        should_alert=should_alert,
        pose_summary=PoseSummary(),
        motion_summary=MotionSummary(),
    )


async def _run_loop(settings, scores, sensor, recovery=None, step_seconds=0.0, mode="require", holder=None):
    """Drive _monitor_camera for len(scores) frames; return (alerts, events, coordinator)."""
    settings.frame_sample_rate = 30.0
    coord, alerts = _coordinator(settings, mode, None)
    if holder is not None:
        holder["coord"] = coord
    coord._fusion.corroborate = AsyncMock(side_effect=sensor)
    coord._pose_estimator.estimate_pose = AsyncMock(return_value=PoseSummary())
    coord._scorer = MagicMock()
    queued = iter(scores)

    def score_frame(camera_name, pose, camera_state, person_detected):
        nxt = next(queued)
        # Mirror the real scorer: cooldown rejects the frame
        if camera_state.cooldown_until and datetime.utcnow() < camera_state.cooldown_until:
            return _score(DetectionStage.REJECTED)
        if nxt.should_alert:
            camera_state.consecutive_fall_frames += 1
            camera_state.fall_candidate_start = camera_state.fall_candidate_start or datetime.utcnow()
        return nxt

    coord._scorer.score_frame.side_effect = score_frame
    coord._scorer.check_recovery.side_effect = recovery or [False] * len(scores)

    start = datetime.utcnow()
    frames = iter(range(len(scores)))

    async def get_frame(_camera):
        i = next(frames, None)
        if i is None or i == len(scores) - 1:
            coord._running = False
        return object(), start + timedelta(seconds=(i or 0) * step_seconds)

    coord._frame_source.get_frame = get_frame
    events: list = []

    async def _ev(e):
        events.append(e)

    coord.on_event(_ev)
    coord._running = True
    await coord._monitor_camera("living_room")
    return alerts, events, coord


async def test_lagging_sensor_retried_after_scorer_drops(settings):
    alerts, events, coord = await _run_loop(
        settings,
        scores=[_score(DetectionStage.CONFIRMED_FALL, True), _score(DetectionStage.POSE_ESTIMATED)],
        sensor=[False, True],
    )
    assert len(alerts) == 1
    assert ReasonCode.SENSOR_CONFIRMED in alerts[0].reason_codes
    assert [e.stage for e in events] == [DetectionStage.FALL_CONFIRMING, DetectionStage.CONFIRMED_FALL]
    assert events[1] is alerts[0]  # published event carries fusion metadata
    assert "living_room" not in coord._pending_fusion


async def test_pending_fusion_cleared_on_recovery(settings):
    alerts, events, coord = await _run_loop(
        settings,
        scores=[_score(DetectionStage.CONFIRMED_FALL, True), _score(DetectionStage.POSE_ESTIMATED)],
        sensor=[False, True],
        recovery=[True],
    )
    assert alerts == []
    assert DetectionStage.CONFIRMED_FALL not in [e.stage for e in events]
    assert "living_room" not in coord._pending_fusion


async def test_pending_fusion_expires(settings):
    settings.fusion_window_seconds = 5
    alerts, _, coord = await _run_loop(
        settings,
        scores=[_score(DetectionStage.CONFIRMED_FALL, True), _score(DetectionStage.POSE_ESTIMATED)],
        sensor=[False, True],
        step_seconds=10,
    )
    assert alerts == []
    assert "living_room" not in coord._pending_fusion


async def test_alert_on_confirmed_frame_clears_pending(settings):
    """Sensor agrees on a later confirmed frame: one alert, no stale retry."""
    alerts, _, coord = await _run_loop(
        settings,
        scores=[
            _score(DetectionStage.CONFIRMED_FALL, True),
            _score(DetectionStage.CONFIRMED_FALL, True),
            _score(DetectionStage.REJECTED),  # scorer cooldown
        ],
        sensor=[False, True, True],
    )
    assert len(alerts) == 1
    assert "living_room" not in coord._pending_fusion


async def test_expiry_checked_on_confirmed_frames(settings):
    """A still-confirmed fall past the window must not alert on a late sensor."""
    settings.fusion_window_seconds = 5
    alerts, _, coord = await _run_loop(
        settings,
        scores=[_score(DetectionStage.CONFIRMED_FALL, True), _score(DetectionStage.CONFIRMED_FALL, True)],
        sensor=[False, True],
        step_seconds=10,
    )
    assert alerts == []
    assert "living_room" not in coord._pending_fusion
    state = coord.camera_states["living_room"]
    assert state.cooldown_until is not None
    assert state.fall_candidate_start is None


async def test_reset_during_sensor_query_discards_alert(settings):
    coord, alerts = _coordinator(settings, "boost", True)

    async def slow_corroborate(camera):
        coord.reset_camera_state(camera)  # user resets while the query is in flight
        return True

    coord._fusion.corroborate = AsyncMock(side_effect=slow_corroborate)
    state = coord.camera_states["living_room"]
    assert await coord._handle_confirmed_fall("living_room", state, _result(), datetime.utcnow()) is None
    assert alerts == []
    assert state.active_alert is False


async def test_recovery_clears_candidate_state(settings):
    _, _, coord = await _run_loop(
        settings,
        scores=[_score(DetectionStage.CONFIRMED_FALL, True), _score(DetectionStage.POSE_ESTIMATED)],
        sensor=[False],
        recovery=[True],
    )
    state = coord.camera_states["living_room"]
    assert state.fall_candidate_start is None
    assert state.consecutive_fall_frames == 0


@pytest.mark.parametrize("mode", ["boost", "require"])
async def test_reset_during_query_in_loop_leaves_no_pending(settings, mode):
    """A discarded (reset) result must not be treated as a sensor rejection."""
    holder: dict = {}
    calls: list = []

    async def corroborate(camera):
        calls.append(camera)
        if len(calls) == 1:
            holder["coord"].reset_camera_state(camera)  # reset while query is in flight
            return False
        return True

    alerts, _, coord = await _run_loop(
        settings,
        scores=[_score(DetectionStage.CONFIRMED_FALL, True), _score(DetectionStage.POSE_ESTIMATED)],
        sensor=corroborate,
        mode=mode,
        holder=holder,
    )
    assert alerts == []
    assert "living_room" not in coord._pending_fusion
    assert len(calls) == 1  # no stale retry on the next frame
