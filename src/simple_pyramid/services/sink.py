"""Канал событий «бэкенд → интерфейс».

Сервисы ничего не знают о pywebview: они вызывают ``sink.emit(event, payload)``, а
реализация (``desktop.emitter``) превращает это в вызов ``window.on<Event>(payload)`` в JS.
"""

from enum import StrEnum
from typing import Any, Protocol


class Section(StrEnum):
    """Блоки данных прибора, которые грузятся и обновляются независимо."""

    IDENTITY = "identity"
    INFO = "info"
    READINGS = "readings"
    LOAD = "load"
    EVENTS = "events"
    REPORT = "report"  # формирование отчёта (только лог задачи)


class StatusKind(StrEnum):
    """Тип сообщения статус-строки."""

    INFO = "info"
    OK = "ok"
    WARN = "warn"
    ERR = "err"


class Sink(Protocol):
    """Получатель событий для интерфейса."""

    def emit(self, event: str, payload: Any = None) -> None:
        """Отправляет событие ``event`` с JSON-совместимым ``payload``."""


class RecordingSink:
    """Sink, который просто копит события (для тестов и отладки)."""

    def __init__(self) -> None:
        self.events: list[tuple[str, Any]] = []

    def emit(self, event: str, payload: Any = None) -> None:
        """Запоминает событие."""
        self.events.append((event, payload))

    def of(self, event: str) -> list[Any]:
        """Все payload'ы события ``event`` по порядку."""
        return [p for e, p in self.events if e == event]
