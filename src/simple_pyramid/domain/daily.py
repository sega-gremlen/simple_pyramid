"""Подневка: показания A+ на начало суток."""

from datetime import date, timedelta

from simple_pyramid.api.models.meterdata import MeterPointData
from simple_pyramid.domain.models import DailyRow

# id параметра «на начало суток» → зона
DAILY_PARAM_MAP: dict[int, str] = {
    -2161: "t0",  # Энергия А+ на начало суток
    4726233: "t1",  # ..., Тарифная зона "День Двухзонный"
    4726791: "t2",  # ..., Тарифная зона "Ночь Двухзонный"
}


def collect_daily_values(points: list[MeterPointData]) -> dict[date, dict[str, float]]:
    """Значения на начало суток по датам, кВт·ч (при дублях побеждает последнее)."""
    by_day: dict[date, dict[str, float]] = {}
    for point in points[:1]:
        for param in point.parameters_data:
            zone = DAILY_PARAM_MAP.get(param.parameter.id)
            if zone is None:
                continue
            for v in param.values:
                if v.value_dt is None or v.value is None:
                    continue
                by_day.setdefault(v.value_dt.date(), {})[zone] = round(v.value / 1000, 3)
    return by_day


def build_daily_rows(points: list[MeterPointData], start: date, end: date) -> list[DailyRow]:
    """Строки подневки за [start, end] — по одной на каждый день периода.

    Расход за сутки = показание на начало следующих суток − показание на начало этих.
    Чтобы посчитать расход последнего дня, данные запрашиваются по ``end + 1`` день.
    """
    by_day = collect_daily_values(points)
    rows = []
    day = start
    while day <= end:
        values = by_day.get(day, {})
        nxt = by_day.get(day + timedelta(days=1), {})
        t0 = values.get("t0")
        consumption = None
        if t0 is not None and nxt.get("t0") is not None:
            consumption = round(nxt["t0"] - t0, 3)
        rows.append(
            DailyRow(
                day=day,
                t0=t0,
                t1=values.get("t1"),
                t2=values.get("t2"),
                consumption=consumption,
            )
        )
        day += timedelta(days=1)
    return rows
