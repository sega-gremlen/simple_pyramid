"""Модели чтения и сбора показаний (``/meterdata/read/``, ``/meterdata/acquire/``)."""

from datetime import datetime
from typing import Annotated

from pydantic import Field

from simple_pyramid.api.models.base import ApiDateTime, ApiModel, NullableList, Ref

CLASSIFIER_ID = 2481

# Фильтр «Самарские РС - Показания текущие общие и 2-х зонные 4 канала»
CURRENT_PARAMETERS: tuple[int, ...] = (
    -2139, 4726239, 4726797,  # А- (общ, день, ночь)
    -1973, 4726597, 4727155,  # А+
    -2143, 4726253, 4726811,  # Р-
    -2141, 4726243, 4726801,  # Р+
)  # fmt: skip

# Фильтр «Самарские РС - Показания на начало суток общие и 2-х зонные А+»
DAILY_PARAMETERS: tuple[int, ...] = (-2161, 4726233, 4726791)

# Источник «прибор учёта»
SOURCE_METER = -3718
CURRENT_SOURCES: tuple[tuple[int, ...], ...] = ((SOURCE_METER,),)
DAILY_SOURCES: tuple[tuple[int, ...], ...] = (
    (-21332,), (-3718,), (-39224,), (-3720,), (-3722,), (-3724,), (-3726,),
)  # fmt: skip


class MeterDataReadRequest(ApiModel):
    """Тело запроса ``POST /meterdata/read/``."""

    classifier_id: int = CLASSIFIER_ID
    instances_ids: list[int]
    parameters: list[int]
    start: ApiDateTime
    finish: ApiDateTime
    sources: list[list[int]]
    require_ratio: bool = False
    require_loses: bool = False


class AcquireRequest(ApiModel):
    """Тело запроса ``POST /meterdata/acquire/`` — задача опроса прибора."""

    classifier_id: int = CLASSIFIER_ID
    instances_ids: list[int]
    parameters: list[int]
    start: ApiDateTime
    finish: ApiDateTime
    absent_only: bool = True


class Parameter(ApiModel):
    """Параметр (канал) показаний."""

    id: int
    caption: str = ""
    unit: str | None = None


class MeterValue(ApiModel):
    """Одно значение параметра."""

    value: float | None = None
    register_dt: datetime | None = None  # когда значение получено с прибора
    value_dt: datetime | None = None  # на какую дату значение (для «на начало суток»)
    source_kind: int | None = None


class ParameterData(ApiModel):
    """Значения одного параметра."""

    parameter: Parameter
    values: Annotated[list[MeterValue], NullableList] = Field(default_factory=list)


class PointWithMeter(ApiModel):
    """Точка учёта с прибором."""

    id: int
    caption: str = ""
    meter: Ref


class MeterPointData(ApiModel):
    """Показания по одной точке учёта."""

    point_with_meter: PointWithMeter
    parameters_data: Annotated[list[ParameterData], NullableList] = Field(default_factory=list)
