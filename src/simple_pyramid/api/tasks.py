"""Ожидание фоновых задач Пирамиды.

Сценарий у всех задач один (опрос прибора, реле, журнала, отчёт):
1. ``POST ...start...`` → id задачи;
2. ``GET getbackgroundtask`` — первый запрос;
3. ``GET getbackgroundtaskstate`` раз в ``interval`` секунд, пока ``isCompleted`` не станет true.

Отмена — обычный ``asyncio`` cancel корутины. Важно: задача на сервере при этом
продолжит выполняться, мы просто перестаём её ждать (API отмены неизвестен).
"""

import asyncio
import logging
from collections.abc import Callable

from simple_pyramid.api.client import PyramidClient
from simple_pyramid.api.errors import TaskTimeoutError
from simple_pyramid.api.models.tasks import LOG_LEVEL_INFO, LOG_TYPE_FULL, LogEntry, TaskState

logger = logging.getLogger(__name__)

LogCallback = Callable[[LogEntry], None]


async def wait_for_task(
    client: PyramidClient,
    task_id: int,
    *,
    interval: float,
    max_wait: float,
    on_log: LogCallback | None = None,
    log_type: int = LOG_TYPE_FULL,
) -> TaskState:
    """Ждёт завершения фоновой задачи и возвращает её финальное состояние.

    Args:
        client: клиент API.
        task_id: id задачи.
        interval: пауза между опросами состояния, сек.
        max_wait: максимальное время ожидания, сек.
        on_log: вызывается для каждой новой человекочитаемой строки лога (level ≥ 1).
        log_type: тип лога в запросе состояния.

    Raises:
        TaskTimeoutError: задача не завершилась за ``max_wait``.
    """
    seen = 0

    def report(state: TaskState) -> None:
        nonlocal seen
        # Лог приходит целиком каждый раз — отдаём только новые строки
        new_entries = state.log[seen:]
        seen = max(seen, len(state.log))
        if on_log is None:
            return
        for entry in new_entries:
            if entry.level >= LOG_LEVEL_INFO and entry.message:
                on_log(entry)

    try:
        async with asyncio.timeout(max_wait):
            state = (await client.get_background_task(task_id)).task_state
            report(state)
            while not state.is_completed:
                await asyncio.sleep(interval)
                state = await client.get_background_task_state(task_id, log_type)
                report(state)
    except TimeoutError as exc:
        raise TaskTimeoutError(
            f"Задача {task_id} не завершилась за {int(max_wait)} с",
        ) from exc

    if state.is_errors_detected:
        logger.warning("Задача %s завершилась с ошибками: %s", task_id, state.information)
    return state
