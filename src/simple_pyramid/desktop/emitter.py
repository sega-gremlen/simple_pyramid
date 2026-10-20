"""Отправка событий в JS: ``emit("Status", {...})`` → ``window.onStatus({...})``."""

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
    """Sink для pywebview-окна."""

    def __init__(self) -> None:
        self.window: JsWindow | None = None

    def emit(self, event: str, payload: Any = None) -> None:
        """Отправляет событие в окно; до появления окна события молча теряются."""
        if self.window is None:
            return
        try:
            self.window.run_js(build_script(event, payload))
        except Exception:
            logger.debug("emit %s не удался", event, exc_info=True)
