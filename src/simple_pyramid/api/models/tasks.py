"""Модели фоновых задач Пирамиды (опрос прибора, отчёты, журнал)."""

from datetime import datetime
from typing import Annotated

from pydantic import Field

from simple_pyramid.api.models.base import ApiModel, NullableList

# logType=2 — «подробный» лог, как в веб-интерфейсе
LOG_TYPE_FULL = 2
# Сообщения level=0 — сырые Tx/Rx пакеты, level=1 — человекочитаемые
LOG_LEVEL_INFO = 1


class LogEntry(ApiModel):
    """Строка лога задачи."""

    message: str = ""
    log_message_type: int = 0
    level: int = 0
    dt: datetime | None = None


class TaskState(ApiModel):
    """Состояние задачи (ответ getbackgroundtaskstate)."""

    is_completed: bool = False
    is_errors_detected: bool = False
    information: str | None = None
    progress: float | None = None
    task_duration: str | None = None
    log: Annotated[list[LogEntry], NullableList] = Field(default_factory=list)


class BackgroundTask(ApiModel):
    """Задача целиком (ответ getbackgroundtask — первый запрос после создания)."""

    id: int
    task_state: TaskState
    short_task_descriptor: str | None = None
