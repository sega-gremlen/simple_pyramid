"""Выбор актуальных текущих показаний.

Пирамида такая охиренная программа, что данные в колонках TO T1 T2 могут быть на разные
даты, и не всегда T1 + T2 == TO. Задача — брать самые актуальные данные.
"""

from dataclasses import dataclass, replace
from datetime import datetime, timedelta

from simple_pyramid.api.models.meterdata import MeterPointData
from simple_pyramid.domain.models import Readings, TariffValues

# id параметра → (направление, зона)
CURRENT_PARAM_MAP: dict[int, tuple[str, str]] = {
    -1973: ("a_plus", "t0"),  # Энергия А+ текущая
    4726597: ("a_plus", "t1"),  # ..., Тарифная зона "День Двухзонный"
    4727155: ("a_plus", "t2"),  # ..., Тарифная зона "Ночь Двухзонный"
    -2139: ("a_minus", "t0"),  # Энергия А- текущая
    4726239: ("a_minus", "t1"),
    4726797: ("a_minus", "t2"),
}

MAX_ZONE_DRIFT = timedelta(hours=24)
# Если TO расходится с T1+T2 больше чем на столько кВт·ч — зонам не верим
MAX_SUM_MISMATCH_KWH = 100


@dataclass(frozen=True)
class Reading:
    """Одно показание: значение (кВт·ч) и момент, когда оно снято."""

    value: float | None = None
    dt: datetime | None = None

    @property
    def present(self) -> bool:
        """Есть и значение, и дата."""
        return self.value is not None and self.dt is not None


EMPTY = Reading()


@dataclass(frozen=True)
class Direction:
    """Показания одного направления (A+ или A−) по зонам."""

    t0: Reading = EMPTY
    t1: Reading = EMPTY
    t2: Reading = EMPTY


def _unpack(r: Reading) -> tuple[float, datetime]:
    """Значение и дата заведомо заполненного показания."""
    if r.value is None or r.dt is None:
        raise ValueError("Ожидалось заполненное показание")
    return r.value, r.dt


def _sum_zones(t1: Reading, t2: Reading) -> Reading:
    """TO = T1 + T2, дата берётся от T2."""
    v1, _ = _unpack(t1)
    v2, dt2 = _unpack(t2)
    return Reading(round(v1 + v2, 2), dt2)


def resolve_direction(d: Direction) -> tuple[Direction, datetime | None]:  # noqa: PLR0911
    """Определяет, какие из значений показаний принимать за истину.

    Returns:
        Исправленные показания и дата выбранных показаний (None — показаний нет).
    """
    t0, t1, t2 = d.t0, d.t1, d.t2
    zones_present = t1.present and t2.present

    # Если везде пусто — пропускаем
    if not (t0.present or t1.present or t2.present):
        return d, None
    # Если есть TO, а какой-то из зон нет — верим TO
    if t0.present and not zones_present:
        return d, t0.dt
    if not t0.present:
        # Есть только T1 и T2 — собираем TO из них
        if zones_present:
            return replace(d, t0=_sum_zones(t1, t2)), t2.dt
        # Есть только одна зона — показываем её как есть
        only = t1 if t1.present else t2
        return d, only.dt

    v0, dt0 = _unpack(t0)
    v1, dt1 = _unpack(t1)
    v2, dt2 = _unpack(t2)
    # Если (время TO - время T1) > 24ч или (время TO - время T2) > 24ч или TO - (T1 + T2) > 100
    if (
        abs(dt0 - dt1) > MAX_ZONE_DRIFT
        or abs(dt0 - dt2) > MAX_ZONE_DRIFT
        or v0 - (v1 + v2) > MAX_SUM_MISMATCH_KWH
    ):
        return Direction(t0=t0), dt0
    # Если |T1 - T2| < 24ч — зоны свежие и согласованные, TO = T1 + T2
    if abs(dt1 - dt2) < MAX_ZONE_DRIFT:
        return replace(d, t0=_sum_zones(t1, t2)), dt2
    # Зоны разъехались между собой — верим только TO (раньше здесь падало исключение)
    return Direction(t0=t0), dt0


def extract_directions(points: list[MeterPointData]) -> dict[str, Direction]:
    """Раскладывает ответ meterdata/read по направлениям и зонам (значения в кВт·ч)."""
    zones: dict[str, dict[str, Reading]] = {"a_plus": {}, "a_minus": {}}
    for point in points[:1]:
        for param in point.parameters_data:
            target = CURRENT_PARAM_MAP.get(param.parameter.id)
            if target is None or not param.values:
                continue
            first = param.values[0]
            if first.value is None:
                continue
            direction, zone = target
            zones[direction][zone] = Reading(round(first.value / 1000, 2), first.register_dt)
    return {name: Direction(**values) for name, values in zones.items()}


def _tariff_values(d: Direction) -> TariffValues:
    """Direction → модель для фронта."""
    return TariffValues(t0=d.t0.value, t1=d.t1.value, t2=d.t2.value)


def build_readings(points: list[MeterPointData]) -> Readings:
    """Текущие показания A+ и A− с общей датой (самой свежей из двух направлений)."""
    directions = extract_directions(points)
    a_plus, plus_dt = resolve_direction(directions["a_plus"])
    a_minus, minus_dt = resolve_direction(directions["a_minus"])
    dates = [dt for dt in (plus_dt, minus_dt) if dt is not None]
    return Readings(
        a_plus=_tariff_values(a_plus),
        a_minus=_tariff_values(a_minus),
        taken_at=max(dates) if dates else None,
    )
