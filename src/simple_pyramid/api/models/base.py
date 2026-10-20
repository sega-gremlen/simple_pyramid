"""Базовые классы и типы для моделей API «Пирамиды»."""

from datetime import datetime
from typing import Annotated, Any

from pydantic import BaseModel, BeforeValidator, ConfigDict, PlainSerializer
from pydantic.alias_generators import to_camel


def format_api_datetime(value: datetime) -> str:
    """Форматирует дату так, как её ждёт «Пирамида»: ``2026-10-20T13:31:10.000``."""
    return value.isoformat(timespec="milliseconds")


def _none_to_list(value: Any) -> Any:
    """Пирамида любит отдавать ``null`` вместо пустого списка — приводим к ``[]``."""
    return [] if value is None else value


# Дата в теле запроса — всегда с миллисекундами, без таймзоны (так шлёт веб-интерфейс)
ApiDateTime = Annotated[datetime, PlainSerializer(format_api_datetime, return_type=str)]

# Список, который в ответе может прийти как null
NullableList = BeforeValidator(_none_to_list)


class ApiModel(BaseModel):
    """Базовая модель запросов/ответов: camelCase-алиасы, лишние поля игнорируются."""

    model_config = ConfigDict(
        alias_generator=to_camel,
        populate_by_name=True,
        extra="ignore",
        frozen=True,
    )

    def to_payload(self) -> Any:
        """Сериализует модель в JSON-совместимый объект для тела запроса."""
        return self.model_dump(mode="json", by_alias=True)


class Ref(ApiModel):
    """Ссылка на объект Пирамиды: ``{"id": ..., "caption": ...}``."""

    id: int
    caption: str = ""
