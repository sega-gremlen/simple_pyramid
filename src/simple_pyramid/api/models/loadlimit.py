"""Модели состояния нагрузки (реле) и лимита мощности."""

from datetime import datetime

from simple_pyramid.api.models.base import ApiModel
from simple_pyramid.api.models.meterdata import CLASSIFIER_ID


class LoadLimitStatesRequest(ApiModel):
    """Тело запроса ``POST /loadlimitmanagement/getmeterpointswithloadandlimitstate/``."""

    classifier_id: int = CLASSIFIER_ID
    instances_ids: list[int]


class StartReadLoadLimitRequest(ApiModel):
    """Тело запроса ``startasynctaskreadloadlimitstates`` — опрос реле и лимита у прибора."""

    meters_id: list[int]


class Operation(ApiModel):
    """Операция чтения/записи (нам нужна только дата)."""

    dt: datetime | None = None


class LoadValue(ApiModel):
    """Значение состояния нагрузки («Включено»/«Отключено»)."""

    id: int | None = None
    caption: str | None = None


class LoadState(ApiModel):
    """Состояние нагрузки (реле)."""

    value: LoadValue | None = None
    value_dt: datetime | None = None
    last_success_read_operation: Operation | None = None


class LimitState(ApiModel):
    """Ограничение мощности."""

    value: float | None = None
    value_dt: datetime | None = None
    last_success_read_operation: Operation | None = None


class LoadLimitPoint(ApiModel):
    """Точка учёта с состояниями реле и лимита."""

    id: int
    load_state: LoadState | None = None
    limit_state: LimitState | None = None
