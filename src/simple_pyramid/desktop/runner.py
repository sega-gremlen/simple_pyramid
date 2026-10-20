"""Один asyncio event loop в фоновом потоке.

pywebview вызывает методы ``js_api`` в своих потоках; они ставят корутины в этот loop
через :meth:`AsyncRunner.submit` и сразу возвращаются — UI не блокируется.
"""

import asyncio
import threading
from collections.abc import Coroutine
from concurrent.futures import Future
from typing import Any


class AsyncRunner:
    """Event loop в отдельном daemon-потоке."""

    def __init__(self) -> None:
        self._loop = asyncio.new_event_loop()
        self._thread = threading.Thread(target=self._run, name="asyncio-loop", daemon=True)
        self._thread.start()

    def _run(self) -> None:
        """Тело потока: крутит loop до остановки."""
        asyncio.set_event_loop(self._loop)
        self._loop.run_forever()

    @property
    def loop(self) -> asyncio.AbstractEventLoop:
        """Сам event loop."""
        return self._loop

    def submit[T](self, coro: Coroutine[Any, Any, T]) -> Future[T]:
        """Запускает корутину в loop'е из любого потока."""
        return asyncio.run_coroutine_threadsafe(coro, self._loop)

    def run[T](self, coro: Coroutine[Any, Any, T], timeout: float | None = None) -> T:
        """Запускает корутину и синхронно ждёт результат (для коротких вызовов из JS)."""
        return self.submit(coro).result(timeout)

    def stop(self) -> None:
        """Останавливает loop."""
        self._loop.call_soon_threadsafe(self._loop.stop)
