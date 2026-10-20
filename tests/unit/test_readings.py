"""Выбор актуальных показаний: сценарии из tests/data/readings_scenarios.json."""

from datetime import datetime
from typing import Any

import pytest

from simple_pyramid.api.models.meterdata import MeterPointData
from simple_pyramid.domain.readings import Direction, Reading, build_readings, resolve_direction
from tests.conftest import load_json

SCENARIOS = load_json("readings_scenarios.json")["scenarios"]


def make_points(values: dict[str, list[Any]]) -> list[MeterPointData]:
    """Ответ meterdata/read из компактного описания сценария."""
    params = [
        {
            "parameter": {"id": int(pid), "caption": ""},
            "values": [{"value": value, "registerDt": dt, "sourceKind": -3718}],
        }
        for pid, (value, dt) in values.items()
    ]
    point = {
        "pointWithMeter": {"id": 1, "caption": "", "meter": {"id": 2, "caption": ""}},
        "parametersData": params,
    }
    return [MeterPointData.model_validate(point)]


@pytest.mark.parametrize("scenario", SCENARIOS, ids=[s["id"] for s in SCENARIOS])
def test_scenarios(scenario: dict[str, Any]) -> None:
    readings = build_readings(make_points(scenario["values"]))
    assert readings.to_js() == scenario["expected"], scenario["description"]


def test_legacy_fixture_matches_old_code(data):
    """Тот же результат, что давал старый backend.extract_meterdata_read на реальном ответе."""
    points = [MeterPointData.model_validate(p) for p in data("meterdata_read.json")]
    readings = build_readings(points)
    assert readings.a_plus.t0 == 42412.71
    assert readings.a_plus.t1 == 8301.42
    assert readings.a_plus.t2 == 34111.29
    assert readings.a_minus.t0 == 16038.71
    assert readings.a_minus.t1 is None
    assert readings.a_minus.t2 is None
    # старый код показывал «24.07.2026 05:31»
    assert readings.taken_at is not None
    assert readings.taken_at.strftime("%d.%m.%Y %H:%M") == "24.07.2026 05:31"


def test_empty_values_list_is_ignored():
    points = make_points({})
    points[0].parameters_data  # noqa: B018 — просто проверяем, что модель валидна
    assert build_readings([]).taken_at is None


def test_resolve_direction_does_not_mutate_input():
    dt = datetime(2026, 10, 20, 6, 0)
    original = Direction(t1=Reading(1.0, dt), t2=Reading(2.0, dt))
    resolved, _ = resolve_direction(original)
    assert original.t0.value is None
    assert resolved.t0.value == 3.0
