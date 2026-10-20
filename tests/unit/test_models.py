"""Pydantic-модели API: разбор реальных ответов и формирование запросов."""

import json
from datetime import datetime

import pytest
from pydantic import ValidationError

from simple_pyramid.api.models.auth import LoginRequest, LoginResponse
from simple_pyramid.api.models.events import (
    EventsRequest,
    Interval,
    PyramidEvent,
    StartReadEventsRequest,
)
from simple_pyramid.api.models.instances import (
    GetInstanceInfoResponse,
    GetInstancesRequest,
    GetInstancesResponse,
)
from simple_pyramid.api.models.loadlimit import (
    LoadLimitPoint,
    LoadLimitStatesRequest,
    StartReadLoadLimitRequest,
)
from simple_pyramid.api.models.meterdata import (
    CURRENT_PARAMETERS,
    AcquireRequest,
    MeterDataReadRequest,
    MeterPointData,
)
from simple_pyramid.api.models.reports import (
    ArchiveReportRequest,
    ReportNode,
    ReportTask,
    build_hourly_report_payload,
)
from simple_pyramid.api.models.tasks import BackgroundTask, TaskState

DT = datetime(2026, 10, 20, 13, 31, 10)


def test_instances_response(data):
    resp = GetInstancesResponse.model_validate(data("instances.json"))
    meter = resp.data[0]
    assert meter.id == 13516722
    assert meter.point.id == 13516725
    assert meter.model == "РиМ 489.26 (СПОДЭС)"
    assert [r.caption for r in meter.routes] == ["Мегафон, +79000000000, 10.0.0.1, порт 4059"]
    assert meter.commissioned_at == datetime(2021, 1, 1)


def test_instances_null_routes_and_empty_data():
    resp = GetInstancesResponse.model_validate(
        {"data": [{"id": 1, "-8295": {"id": 2, "caption": "x"}, "-3134": None}]}
    )
    assert resp.data[0].routes == []
    assert GetInstancesResponse.model_validate({"data": None}).data == []


def test_instances_missing_point_is_validation_error():
    with pytest.raises(ValidationError, match="-8295"):
        GetInstancesResponse.model_validate({"data": [{"id": 1}]})


def test_instances_request_payload():
    payload = GetInstancesRequest.by_meter_number("01536145").to_payload()
    assert payload["classId"] == -1646
    assert payload["userCustomized"] is False
    assert payload["options"]["take"] == "2"
    assert json.loads(payload["options"]["filter"]) == ["-1494", "contains", "01536145"]
    assert json.loads(payload["options"]["sort"]) == [{"selector": "id", "desc": False}]


def test_instance_info(data):
    info = GetInstanceInfoResponse.model_validate(data("instance_info.json"))
    assert info.instance.accounts[0].caption == "И. И. И. №013300000001"
    assert info.instance.full_path is not None
    assert info.instance.full_path.endswith("ул Примерная, д 1")


def test_meterdata_read(data):
    points = [MeterPointData.model_validate(p) for p in data("meterdata_read.json")]
    params = {p.parameter.id: p for p in points[0].parameters_data}
    assert set(params) == set(CURRENT_PARAMETERS)
    value = params[-1973].values[0]
    assert value.value == 42412710.0
    assert value.register_dt == datetime(2026, 7, 24, 5, 31, 27, 802000)


def test_meterdata_read_request_payload():
    payload = MeterDataReadRequest(
        instances_ids=[21586967], parameters=[-2139], start=DT, finish=DT, sources=[[-3718]]
    ).to_payload()
    assert payload == {
        "classifierId": 2481,
        "instancesIds": [21586967],
        "parameters": [-2139],
        "start": "2026-10-20T13:31:10.000",
        "finish": "2026-10-20T13:31:10.000",
        "sources": [[-3718]],
        "requireRatio": False,
        "requireLoses": False,
    }


def test_acquire_request_payload():
    payload = AcquireRequest(
        instances_ids=[21586967], parameters=list(CURRENT_PARAMETERS),
        start=DT.replace(hour=0, minute=0, second=0), finish=DT,
    ).to_payload()  # fmt: skip
    assert payload["absentOnly"] is True
    assert payload["start"] == "2026-10-20T00:00:00.000"
    assert payload["parameters"] == list(CURRENT_PARAMETERS)


def test_load_limit_models(data):
    morning = LoadLimitPoint.model_validate(data("loadlimit_morning.json")[0])
    assert morning.load_state is not None
    assert morning.load_state.value is not None
    assert morning.load_state.value.caption == "Включено"
    assert morning.limit_state is not None
    assert morning.limit_state.value == 15000.0
    assert LoadLimitStatesRequest(instances_ids=[1]).to_payload() == {
        "classifierId": 2481,
        "instancesIds": [1],
    }
    assert StartReadLoadLimitRequest(meters_id=[21586965]).to_payload() == {"metersId": [21586965]}


def test_events_models(data):
    events = [PyramidEvent.model_validate(e) for e in data("events.json")]
    assert events[0].event_type == "Выполнен анализ времени устройства"
    assert events[0].dt == datetime(2026, 10, 19, 6, 44, 13, 564000)
    payload = EventsRequest(
        ids=[21587336],
        intervals=[Interval(begin=datetime(2026, 10, 13), end=datetime(2026, 10, 20))],
    ).to_payload()
    assert payload == {
        "ids": [21587336],
        "eventsIds": None,
        "startDt": None,
        "endDt": None,
        "intervals": [{"begin": "2026-10-13T00:00:00.000", "end": "2026-10-20T00:00:00.000"}],
    }
    start = StartReadEventsRequest(
        event_sources_int_ref_names=[20845178], start_date=datetime(2026, 10, 20), end_date=DT
    ).to_payload()
    assert start == {
        "eventSourcesIntRefNames": [20845178],
        "startDate": "2026-10-20T00:00:00.000",
        "endDate": "2026-10-20T13:31:10.000",
    }


def test_task_models(data):
    started = BackgroundTask.model_validate(data("task_started.json"))
    assert started.id == -1876
    assert started.task_state.is_completed is False
    done = TaskState.model_validate(data("task_state_done.json"))
    assert done.is_completed is True
    assert len(done.log) == 9
    assert TaskState.model_validate({"isCompleted": False, "log": None}).log == []


def test_login_models():
    assert LoginRequest(username="u", password="p").to_payload() == {
        "username": "u",
        "password": "p",
        "tokens": None,
    }
    resp = LoginResponse.model_validate({"tokens": {"accessToken": "t"}, "userId": 688})
    assert resp.tokens.access_token == "t"
    assert resp.user_id == 688


def test_hourly_report_payload_matches_legacy(data):
    """Payload почасовки совпадает с тем, что слала старая версия (кроме типа id: теперь int)."""
    payload = build_hourly_report_payload(
        datetime(2026, 10, 1), datetime(2026, 10, 20), [ReportNode(id=13516725, caption="CAPTION")]
    )
    legacy = data("hourly_report_payload.json")
    legacy[0]["values"][0]["asInstanceLink"]["id"] = 13516725
    assert payload == legacy


def test_report_task_and_archive_request():
    task = ReportTask.model_validate({"taskId": 5, "archiveEntryId": "abc"})
    assert task.task_id == 5
    body = ArchiveReportRequest(user_id=688, archive_entry_id="abc").to_payload()
    assert body["userId"] == 688
    assert body["keepNotification"] is False
    assert body["fileName"].startswith("02.01")


def test_models_are_frozen():
    node = ReportNode(id=1, caption="x")
    with pytest.raises(ValidationError):
        node.id = 2  # type: ignore[misc]
