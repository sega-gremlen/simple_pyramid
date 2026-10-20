"""Асинхронный ping маршрутов.

Одиночные ping-пакеты отправляются до первого успеха, но не более ``max_attempts`` попыток.
Остановка — обычный cancel корутины.
"""

import asyncio
import logging
import subprocess
import sys
from collections.abc import Callable

logger = logging.getLogger(__name__)

PING_TIMEOUT_MS = 1000
PAUSE_BETWEEN_ATTEMPTS = 0.5

AttemptCallback = Callable[[int, int], None]


def ping_command(ip: str) -> list[str]:
    """Команда ping одного пакета с таймаутом 1 с для текущей ОС."""
    if sys.platform == "win32":
        # -n 1 - один пакет, -w 1000 - таймаут 1 секунда
        return ["ping", "-n", "1", "-w", str(PING_TIMEOUT_MS), ip]
    # -c 1 - один пакет, -W 1 - таймаут 1 секунда
    return ["ping", "-c", "1", "-W", str(PING_TIMEOUT_MS // 1000), ip]


async def ping_once(ip: str) -> bool:
    """Один ping. True — ответ получен."""
    kwargs = {}
    if sys.platform == "win32":
        kwargs["creationflags"] = subprocess.CREATE_NO_WINDOW
    try:
        proc = await asyncio.create_subprocess_exec(
            *ping_command(ip),
            stdout=asyncio.subprocess.DEVNULL,
            stderr=asyncio.subprocess.DEVNULL,
            **kwargs,  # type: ignore[arg-type]
        )
    except OSError:
        logger.exception("Не удалось запустить ping %s", ip)
        return False
    try:
        async with asyncio.timeout(PING_TIMEOUT_MS / 1000 + 2):  # таймаут на всякий случай
            return await proc.wait() == 0
    except (TimeoutError, asyncio.CancelledError):
        if proc.returncode is None:
            proc.kill()
        raise


async def ping_until_success(
    ip: str,
    *,
    max_attempts: int,
    on_attempt: AttemptCallback | None = None,
    ping: Callable[[str], asyncio.Future[bool]] | None = None,
    pause: float = PAUSE_BETWEEN_ATTEMPTS,
) -> int | None:
    """Пингует до первого ответа.

    Returns:
        Номер успешной попытки или None, если ответа так и не было.
    """
    do_ping = ping or ping_once
    for attempt in range(1, max_attempts + 1):
        if on_attempt:
            on_attempt(attempt, max_attempts)
        try:
            ok = await do_ping(ip)
        except TimeoutError:
            ok = False
        if ok:
            return attempt
        # Небольшая пауза между попытками
        if attempt < max_attempts:
            await asyncio.sleep(pause)
    return None
