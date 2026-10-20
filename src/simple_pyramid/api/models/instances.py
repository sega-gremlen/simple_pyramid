"""Модели поиска прибора учёта и информации о точке учёта.

Поля с числовыми ключами (``"-8295"`` и т.п.) — это id атрибутов в Пирамиде,
у моделей им даны человеческие имена.
"""

import json
from datetime import datetime
from typing import Annotated

from pydantic import Field

from simple_pyramid.api.models.base import ApiModel, NullableList, Ref

# Класс «Прибор учёта» в Пирамиде
METER_CLASS_ID = -1646
# Атрибут «Заводской номер»
METER_NUMBER_ATTR = "-1494"


class GetInstancesOptions(ApiModel):
    """Параметры выборки (формат DevExtreme, строки с JSON внутри)."""

    take: str = "2"
    sort: str = json.dumps([{"selector": "id", "desc": False}])
    filter: str


class GetInstancesRequest(ApiModel):
    """Тело запроса ``POST /rdinstance/getinstances/``."""

    class_id: int = METER_CLASS_ID
    user_customized: bool = False
    options: GetInstancesOptions

    @classmethod
    def by_meter_number(cls, meter_num: str) -> "GetInstancesRequest":
        """Запрос приборов, у которых заводской номер содержит ``meter_num``.

        ``take=2`` — чтобы отличить «найден ровно один» от «найдено несколько».
        """
        flt = json.dumps([METER_NUMBER_ATTR, "contains", meter_num], ensure_ascii=False)
        return cls(options=GetInstancesOptions(filter=flt))


class MeterInstance(ApiModel):
    """Прибор учёта из ответа getinstances."""

    id: int  # id самого прибора (нужен для управления нагрузкой)
    caption: str = ""
    number: str | None = Field(default=None, alias="-1494")
    model: str | None = Field(default=None, alias="-56855")
    point: Ref = Field(alias="-8295")  # точка учёта: её id — «instance id» почти во всех запросах
    routes: Annotated[list[Ref], NullableList] = Field(default_factory=list, alias="-3134")
    commissioned_at: datetime | None = Field(default=None, alias="-1498")


class GetInstancesResponse(ApiModel):
    """Ответ getinstances."""

    data: Annotated[list[MeterInstance], NullableList] = Field(default_factory=list)


class PointInstance(ApiModel):
    """Точка учёта из ответа getinstanceinfo."""

    id: int
    accounts: Annotated[list[Ref], NullableList] = Field(default_factory=list, alias="-10024")
    full_path: str | None = Field(default=None, alias="-13379")


class GetInstanceInfoResponse(ApiModel):
    """Ответ ``GET /rdinstance/getinstanceinfo/``."""

    instance: PointInstance
