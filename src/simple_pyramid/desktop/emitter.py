"""Отправка событий в JS: ``emit("Status", {...})`` → ``window.onStatus({...})``.

Событие уходит во все открытые окна программы (главное, «Подневка», «События»):
каждая страница обрабатывает только то, что ей нужно, остальное игнорирует.
"""

import json
import logging
from typing import Any, Protocol

logger = logging.getLogger(__name__)


class JsWindow(Protocol):
    """То, что нужно от окна pywebview."""

    def run_js(self, script: str) -> Any:
        """Выполняет JS без ожидания результата."""


def build_script(event: str, payload: Any) -> str:
    """JS-код вызова обработчика ``window.on<event>`` (если он объявлен)."""
    data = json.dumps(payload, ensure_ascii=False, default=str)
    return f"window.on{event} && window.on{event}({data})"


class WindowEmitter:
    """Sink для pywebview-окон."""

    def __init__(self) -> None:
        self.windows: list[JsWindow] = []

    @property
    def window(self) -> JsWindow | None:
        """Главное окно (первое подключённое)."""
        return self.windows[0] if self.windows else None

    @window.setter
    def window(self, value: JsWindow | None) -> None:
        """Подключает главное окно."""
        self.windows = [value] if value is not None else []

    def add(self, window: JsWindow) -> None:
        """Подключает дополнительное окно."""
        self.windows.append(window)

    def remove(self, window: JsWindow) -> None:
        """Отключает закрытое окно."""
        self.windows = [w for w in self.windows if w is not window]

    def emit(self, event: str, payload: Any = None) -> None:
        """Отправляет событие во все окна; до появления окон события молча теряются."""
        script = build_script(event, payload)
        for window in list(self.windows):
            try:
                window.run_js(script)
            except Exception:
                logger.debug("emit %s не удался", event, exc_info=True)
