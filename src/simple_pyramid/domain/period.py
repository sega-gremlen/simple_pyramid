"""Период выгрузки и его проверка «на адекватность»."""

from datetime import date, datetime
from typing import Self

from pydantic import BaseModel, ConfigDict, ValidationError, field_validator, model_validator

DATE_FORMAT = "%d.%m.%Y"
MIN_DATE = date(2015, 1, 1)


class Period(BaseModel):
    """Период ``[start, end]`` в днях. Принимает даты строками ``ДД.ММ.ГГГГ``."""

    model_config = ConfigDict(frozen=True)

    start: date
    end: date

    @field_validator("start", "end", mode="before")
    @classmethod
    def _parse(cls, value: object) -> object:
        """Разбирает ``ДД.ММ.ГГГГ``; несуществующие даты (67-е число) отклоняются."""
        if isinstance(value, str):
            text = value.strip()
            try:
                return datetime.strptime(text, DATE_FORMAT).date()
            except ValueError:
                msg = f"Неверная дата «{text}» — нужен формат ДД.ММ.ГГГГ"
                raise ValueError(msg) from None
        return value

    @model_validator(mode="after")
    def _check_range(self) -> Self:
        """Даты не раньше 2015 года, не в будущем, начало не позже конца."""
        today = date.today()
        for value in (self.start, self.end):
            if value < MIN_DATE:
                msg = f"Дата {value:%d.%m.%Y} слишком ранняя (не раньше {MIN_DATE:%d.%m.%Y})"
                raise ValueError(msg)
            if value > today:
                msg = f"Дата {value:%d.%m.%Y} ещё не наступила"
                raise ValueError(msg)
        if self.start > self.end:
            raise ValueError("Начало периода позже окончания")
        return self

    @property
    def days(self) -> int:
        """Количество дней в периоде (включительно)."""
        return (self.end - self.start).days + 1


def parse_period(start: str, end: str) -> Period:
    """Проверяет период. Ошибка — ``ValueError`` с понятным текстом."""
    try:
        return Period.model_validate({"start": start, "end": end})
    except ValidationError as exc:
        first = exc.errors()[0]
        message = str(first.get("ctx", {}).get("error") or first["msg"])
        raise ValueError(message.removeprefix("Value error, ")) from None
