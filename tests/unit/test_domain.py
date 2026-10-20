"""Доменная логика: прибор, точка учёта, нагрузка, события, подневка, период."""

from datetime import date, datetime, timedelta

import pytest

from simple_pyramid.api.errors import AmbiguousMeterError, MeterNotFoundError
from simple_pyramid.api.models.events import PyramidEvent
from simple_pyramid.api.models.instances import GetInstanceInfoResponse, GetInstancesResponse
from simple_pyramid.api.models.loadlimit import LoadLimitPoint
from simple_pyramid.api.models.meterdata import MeterPointData
from simple_pyramid.domain.daily import build_daily_rows, collect_daily_values
from simple_pyramid.domain.events import alarm_summary, events_page, to_meter_events
from simple_pyramid.domain.load import build_load_info, relay_is_on
from simple_pyramid.domain.meter import build_identity, build_point_info, extract_ip, normalize_ip
from simple_pyramid.domain.period import parse_period


# ---------------------------------------------------------------- прибор
def test_build_identity(data):
    identity = build_identity(
        "1536145", GetInstancesResponse.model_validate(data("instances.json"))
    )
    assert identity.meter_id == 13516722
    assert identity.point_id == 13516725
    assert identity.model == "РиМ 489.26 (СПОДЭС)"
    assert identity.routes[0].ip == "10.0.0.1"
    assert identity.routes[0].id == "r0"


def test_build_identity_not_found_and_ambiguous(data):
    with pytest.raises(MeterNotFoundError, match="убрать первый 0"):
        build_identity("1", GetInstancesResponse(data=[]))
    raw = data("instances.json")
    raw["data"] = raw["data"] * 2
    with pytest.raises(AmbiguousMeterError):
        build_identity("1", GetInstancesResponse.model_validate(raw))


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("Мегафон, +79270018410, 172.17.100.1, порт 4059", ("172.17.100.1", "172.17.100.1")),
        ("МТС, 010.010.020.030, порт 1", ("010.010.020.030", "10.10.20.30")),
        ("Без IP-адреса", None),
    ],
)
def test_extract_ip(text, expected):
    assert extract_ip(text) == expected


def test_normalize_ip():
    assert normalize_ip("001.002.003.004") == "1.2.3.4"


def test_build_point_info(data):
    info = build_point_info(GetInstanceInfoResponse.model_validate(data("instance_info.json")))
    assert info.account == "И. И. И. №013300000001"
    assert info.account_number == "013300000001"
    assert info.address == "Сызранский р-н, село Тестовое, ул Примерная, д 1"


def test_build_point_info_without_account():
    info = build_point_info(GetInstanceInfoResponse.model_validate({"instance": {"id": 1}}))
    assert info.account is None
    assert info.address is None


def test_point_info_account_without_number():
    resp = GetInstanceInfoResponse.model_validate(
        {"instance": {"id": 1, "-10024": [{"id": 2, "caption": "Без номера"}]}}
    )
    info = build_point_info(resp)
    assert info.account == "Без номера"
    assert info.account_number is None


# ---------------------------------------------------------------- нагрузка
def test_load_info_morning(data):
    load = build_load_info(
        [LoadLimitPoint.model_validate(p) for p in data("loadlimit_morning.json")]
    )
    assert load.relay == "Включено"
    assert load.relay_on is True
    assert load.relay_at == datetime(2026, 10, 20, 6, 45, 31, 352000)
    assert load.limit == 15000.0
    assert load.limit_at == datetime(2026, 10, 20, 6, 45, 30, 232000)


def test_load_info_after_refresh_takes_operation_dt(data):
    points = [LoadLimitPoint.model_validate(p) for p in data("loadlimit_after_refresh.json")]
    load = build_load_info(points)
    assert load.relay_at == datetime(2026, 10, 20, 13, 15, 10, 712000)
    assert load.limit_at == datetime(2026, 10, 20, 13, 15, 14, 25000)


def test_load_info_empty():
    assert build_load_info([]).relay is None
    assert build_load_info([LoadLimitPoint(id=1)]).limit is None


@pytest.mark.parametrize(
    ("caption", "expected"),
    [
        ("Включено", True),
        ("Отключено", False),
        ("выключено", False),
        ("Неизвестно", None),
        (None, None),
    ],
)
def test_relay_is_on(caption, expected):
    assert relay_is_on(caption) is expected


# ---------------------------------------------------------------- события
@pytest.fixture
def events(data):
    return to_meter_events(PyramidEvent.model_validate(e) for e in data("events.json"))


def test_events_sorted_and_flagged(events):
    assert [e.dt for e in events] == sorted((e.dt for e in events), reverse=True)
    opening = [e for e in events if e.event_type == "Вскрытие элемента устройства"]
    assert all(e.alarm and e.important for e in opening)
    assert opening[-1].description == "Вскрытие клеммной крышки"  # пробелы обрезаны
    load_off = next(e for e in events if e.event_type == "Отключение нагрузки")
    assert load_off.important and not load_off.alarm
    assert load_off.description == ""  # null → пустая строка


def test_alarm_summary(events):
    alarms = alarm_summary(events)
    assert len(alarms) == 1
    assert alarms[0].event_type == "Вскрытие элемента устройства"
    assert alarms[0].count == 2
    assert alarms[0].last_at == datetime(2026, 10, 17, 3, 0)


def test_events_page(events):
    page = events_page(events, offset=0, limit=2, important_only=False)
    assert page.total == 6
    assert len(page.items) == 2
    assert page.has_more
    last = events_page(events, offset=4, limit=10, important_only=False)
    assert len(last.items) == 2
    assert not last.has_more
    important = events_page(events, offset=0, limit=10, important_only=True)
    assert important.total == 3
    assert all(e.important for e in important.items)
    assert events_page(events, offset=-5, limit=1, important_only=False).offset == 0


# ---------------------------------------------------------------- подневка
def test_daily_rows(data):
    points = [MeterPointData.model_validate(p) for p in data("meter_daily_data.json")]
    values = collect_daily_values(points)
    first_day = min(values)
    rows = build_daily_rows(points, first_day, first_day + timedelta(days=2))
    assert [r.day for r in rows] == [first_day + timedelta(days=i) for i in range(3)]
    assert rows[0].t0 == 42412.71
    assert rows[0].t1 == 8301.42
    assert rows[0].t2 == 34111.29
    assert rows[0].consumption == round(values[first_day + timedelta(days=1)]["t0"] - 42412.71, 3)


def test_daily_rows_missing_days_are_empty():
    rows = build_daily_rows([], date(2026, 1, 1), date(2026, 1, 3))
    assert len(rows) == 3
    assert all(r.t0 is None and r.consumption is None for r in rows)


# ---------------------------------------------------------------- период
def test_period_ok():
    period = parse_period("01.10.2026", "20.10.2026")
    assert period.start == date(2026, 10, 1)
    assert period.days == 20


@pytest.mark.parametrize(
    ("start", "end", "message"),
    [
        ("67.10.2026", "20.10.2026", "Неверная дата «67.10.2026»"),
        ("2026-10-01", "20.10.2026", "ДД.ММ.ГГГГ"),
        ("01.01.1970", "20.10.2026", "слишком ранняя"),
        ("01.01.2099", "01.01.2099", "ещё не наступила"),
        ("20.10.2026", "01.10.2026", "позже окончания"),
    ],
)
def test_period_invalid(start, end, message):
    with pytest.raises(ValueError, match=message):
        parse_period(start, end)
