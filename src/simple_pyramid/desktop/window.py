"""Создание окон pywebview и запуск приложения.

Главное окно — поиск прибора. «Подневка» и «События» открываются отдельными окнами
той же программы (тот же мост ``Api``), не завися от размеров главного.
"""

import logging
import sys
from pathlib import Path
from typing import Any

import webview

from simple_pyramid.config import Settings, get_settings
from simple_pyramid.desktop.bridge import APP_TITLE, Api
from simple_pyramid.desktop.emitter import WindowEmitter

logger = logging.getLogger(__name__)

WIDTH = 607
HEIGHT = 520
MIN_WIDTH = 607
MIN_HEIGHT = 360
BACKGROUND = "#FAFAF9"

# Дополнительные окна: страница и размеры
CHILD_WINDOWS: dict[str, dict[str, Any]] = {
    "daily": {"page": "ui/daily.html", "width": 640, "height": 680, "min_size": (520, 420)},
    "events": {"page": "ui/events.html", "width": 840, "height": 640, "min_size": (600, 400)},
}


def resource_path(rel: str) -> Path:
    """Путь к ресурсу: работает и из исходников, и из сборки PyInstaller."""
    base = getattr(sys, "_MEIPASS", None)
    if base:
        return Path(base) / "simple_pyramid" / rel
    return Path(__file__).resolve().parent.parent / rel


class PywebviewWindow:
    """Адаптер окон pywebview под :class:`~simple_pyramid.desktop.bridge.WindowControl`."""

    def __init__(self, window: Any, emitter: WindowEmitter, api: Api) -> None:
        self._window = window
        self._emitter = emitter
        self._api = api
        self._children: dict[str, Any] = {}
        window.events.closed += self._close_children

    def set_title(self, title: str) -> None:
        """Меняет заголовок главного окна Windows."""
        self._window.set_title(title)

    def grow_height(self, delta: int) -> None:
        """Меняет высоту окна (размеры pywebview — в логических пикселях, как в CSS)."""
        width, height = self._window.width, self._window.height
        self._window.resize(width, max(MIN_HEIGHT, height + delta))

    def choose_folder(self, kind: str | None = None) -> str | None:
        """Диалог выбора папки (поверх окна ``kind`` или главного)."""
        owner = self._children.get(kind or "", self._window)
        result = owner.create_file_dialog(webview.FileDialog.FOLDER)
        return str(result[0]) if result else None

    def open_child(self, kind: str, title: str) -> None:
        """Открывает окно ``kind`` или поднимает уже открытое."""
        existing = self._children.get(kind)
        if existing is not None:
            existing.set_title(title)
            existing.restore()
            existing.show()
            return
        spec = CHILD_WINDOWS[kind]
        child = webview.create_window(
            title,
            str(resource_path(spec["page"])),
            js_api=self._api,
            width=spec["width"],
            height=spec["height"],
            min_size=spec["min_size"],
            background_color=BACKGROUND,
        )
        if child is None:
            return
        self._children[kind] = child
        self._emitter.add(child)

        def on_closed() -> None:
            self._children.pop(kind, None)
            self._emitter.remove(child)

        child.events.closed += on_closed

    def set_child_title(self, kind: str, title: str) -> None:
        """Обновляет заголовок дополнительного окна, если оно открыто."""
        child = self._children.get(kind)
        if child is not None:
            child.set_title(title)

    def _close_children(self) -> None:
        """Главное окно закрыто — закрываем и дополнительные."""
        for child in list(self._children.values()):
            try:
                child.destroy()
            except Exception:
                logger.debug("Окно уже закрыто", exc_info=True)

    def close(self) -> None:
        """Закрывает программу."""
        self._window.destroy()


def run(settings: Settings | None = None) -> None:
    """Создаёт главное окно и запускает GUI-цикл (блокирует до закрытия)."""
    settings = settings or get_settings()
    emitter = WindowEmitter()
    api = Api(settings, emitter)
    window = webview.create_window(
        APP_TITLE,
        str(resource_path("ui/index.html")),
        js_api=api,
        width=WIDTH,
        height=HEIGHT,
        min_size=(MIN_WIDTH, MIN_HEIGHT),
        background_color=BACKGROUND,
    )
    emitter.window = window
    api._attach_window(PywebviewWindow(window, emitter, api))

    webview.start(gui="edgechromium", debug=settings.debug)
