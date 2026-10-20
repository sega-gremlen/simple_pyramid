"""Доменные модели — то, чем оперирует приложение и что уходит во фронт (camelCase JSON)."""

from datetime import date, datetime
from typing import Annotated, Any

from pydantic import BaseModel, ConfigDict, Field, PlainSerializer
from pydantic.alias_generators import to_camel


def _js_datetime(value: datetime) -> str:
    """Дата для JS: ISO без долей секунды и таймзоны (локальное время сервера)."""
    return value.isoformat(timespec="seconds")


JsDateTime = Annotated[datetime, PlainSerializer(_js_datetime, return_type=str)]


class DtoModel(BaseModel):
    """База доменных моделей: неизменяемые, сериализуются во фронт в camelCase."""

    model_config = ConfigDict(alias_generator=to_camel, populate_by_name=True, frozen=True)

    def to_js(self) -> dict[str, Any]:
        """JSON-совместимый словарь для передачи в JS."""
        return self.model_dump(mode="json", by_alias=True)


class Route(DtoModel):
    """Маршрут связи с прибором (модем/канал)."""

    id: str
    text: str
    ip: str | None = None  # нормализованный IP — для пинга и копирования
    ip_text: str | None = None  # IP ровно как в тексте маршрута — для подсветки


class MeterIdentity(DtoModel):
    """Найденный прибор: всё, что приходит первым запросом."""

    meter_num: str
    meter_id: int
    point_id: int
    model: str | None = None
    caption: str = ""
    point_caption: str = ""
    routes: list[Route] = Field(default_factory=list)


class PointInfo(DtoModel):
    """Точка учёта: договор и адрес."""

    account: str | None = None
    account_number: str | None = None  # часть после «№» — то, что обычно копируют
    address: str | None = None
    full_path: str | None = None


class TariffValues(DtoModel):
    """Показания по тарифным зонам, кВт·ч."""

    t0: float | None = None
    t1: float | None = None
    t2: float | None = None


class Readings(DtoModel):
    """Текущие показания A+ и A−."""

    a_plus: TariffValues = Field(default_factory=TariffValues)
    a_minus: TariffValues = Field(default_factory=TariffValues)
    taken_at: JsDateTime | None = None


class LoadInfo(DtoModel):
    """Состояние нагрузки: реле и лимит мощности (значения как пришли из Пирамиды)."""

    relay: str | None = None
    relay_on: bool | None = None
    relay_at: JsDateTime | None = None
    limit: float | None = None
    limit_at: JsDateTime | None = None


class MeterEvent(DtoModel):
    """Событие журнала."""

    dt: JsDateTime
    event_type: str
    description: str = ""
    important: bool = False
    alarm: bool = False


class AlarmItem(DtoModel):
    """Тревожный тип события, встречающийся в истории прибора."""

    event_type: str
    count: int
    last_at: JsDateTime


class EventsPage(DtoModel):
    """Порция событий для бесконечной прокрутки."""

    items: list[MeterEvent]
    total: int
    offset: int
    has_more: bool


class DailyRow(DtoModel):
    """Строка подневки: показания на начало суток и расход за сутки, кВт·ч."""

    day: date
    t0: float | None = None
    t1: float | None = None
    t2: float | None = None
    consumption: float | None = None
