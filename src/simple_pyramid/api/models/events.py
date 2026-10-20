"""Модели журнала событий."""

from datetime import datetime

from simple_pyramid.api.models.base import ApiDateTime, ApiModel


class Interval(ApiModel):
    """Интервал времени для выборки событий."""

    begin: ApiDateTime
    end: ApiDateTime


class EventsRequest(ApiModel):
    """Тело запроса ``POST /events/geteventsforobjects/``."""

    ids: list[int]
    events_ids: list[int] | None = None
    start_dt: ApiDateTime | None = None
    end_dt: ApiDateTime | None = None
    intervals: list[Interval]


class StartReadEventsRequest(ApiModel):
    """Тело запроса ``POST /events/startreadeventsasync/`` — вычитать журнал с прибора."""

    event_sources_int_ref_names: list[int]
    start_date: ApiDateTime
    end_date: ApiDateTime


class PyramidEvent(ApiModel):
    """Событие из журнала."""

    dt: datetime
    event_type: str = ""
    description: str | None = None
    compound_key: str | None = None
    category_caption: str | None = None
