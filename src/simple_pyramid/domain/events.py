"""Журнал событий: какие события важные, какие тревожные."""

from collections.abc import Iterable

from simple_pyramid.api.models.events import PyramidEvent
from simple_pyramid.domain.models import AlarmItem, EventsPage, MeterEvent

# Тревожные события — по ним показываем алярм-иконку
ALARM_EVENT_TYPES: frozenset[str] = frozenset(
    {
        "Вскрытие элемента устройства",
        "Закрытие элемента устройства",
        "Попытка несанкционированного доступа",
        "Попытка мошенничества",
        "Выполнен сброс состояний пломб",
        "Вскрытие элементов",
    }
)

# Фильтр «Только важные»
IMPORTANT_EVENT_TYPES: frozenset[str] = ALARM_EVENT_TYPES | {
    "Отключение нагрузки",
    "Включение нагрузки",
    "Разрешение включения нагрузки",
}


def _normalize(event_type: str) -> str:
    """Сравниваем типы без учёта регистра и пробелов по краям."""
    return event_type.strip().casefold()


_ALARM = {_normalize(t) for t in ALARM_EVENT_TYPES}
_IMPORTANT = {_normalize(t) for t in IMPORTANT_EVENT_TYPES}


def to_meter_events(events: Iterable[PyramidEvent]) -> list[MeterEvent]:
    """API-события → доменные, от свежих к старым."""
    result = [
        MeterEvent(
            dt=e.dt,
            event_type=e.event_type,
            description=(e.description or "").strip(),
            important=_normalize(e.event_type) in _IMPORTANT,
            alarm=_normalize(e.event_type) in _ALARM,
        )
        for e in events
    ]
    result.sort(key=lambda e: e.dt, reverse=True)
    return result


def alarm_summary(events: Iterable[MeterEvent]) -> list[AlarmItem]:
    """Тревожные типы событий с количеством и датой последнего случая."""
    acc: dict[str, AlarmItem] = {}
    for e in events:
        if not e.alarm:
            continue
        prev = acc.get(e.event_type)
        if prev is None:
            acc[e.event_type] = AlarmItem(event_type=e.event_type, count=1, last_at=e.dt)
        else:
            acc[e.event_type] = AlarmItem(
                event_type=e.event_type,
                count=prev.count + 1,
                last_at=max(prev.last_at, e.dt),
            )
    return sorted(acc.values(), key=lambda a: a.last_at, reverse=True)


def events_page(
    events: list[MeterEvent], *, offset: int, limit: int, important_only: bool
) -> EventsPage:
    """Порция событий для бесконечной прокрутки."""
    source = [e for e in events if e.important] if important_only else events
    offset = max(offset, 0)
    items = source[offset : offset + limit]
    return EventsPage(
        items=items,
        total=len(source),
        offset=offset,
        has_more=offset + len(items) < len(source),
    )
