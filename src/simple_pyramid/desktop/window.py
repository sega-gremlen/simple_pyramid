"""Создание окна pywebview и запуск приложения."""

import logging
import sys
from pathlib import Path
from typing import Any

import webview

from simple_pyramid.config import Settings, get_settings
from simple_pyramid.desktop.bridge import APP_TITLE, Api
from simple_pyramid.desktop.emitter import WindowEmitter

logger = logging.getLogger(__name__)

WIDTH = 782
HEIGHT = 520
MIN_WIDTH = 714
MIN_HEIGHT = 360
BACKGROUND = "#FAFAF9"


def resource_path(rel: str) -> Path:
    """Путь к ресурсу: работает и из исходников, и из сборки PyInstaller."""
    base = getattr(sys, "_MEIPASS", None)
    if base:
        return Path(base) / "simple_pyramid" / rel
    return Path(__file__).resolve().parent.parent / rel


class PywebviewWindow:
    """Адаптер окна pywebview под :class:`~simple_pyramid.desktop.bridge.WindowControl`."""

    def __init__(self, window: Any) -> None:
        self._window = window

    def set_title(self, title: str) -> None:
        """Меняет заголовок окна Windows."""
        self._window.set_title(title)

    def grow_height(self, delta: int) -> None:
        """Меняет высоту окна (размеры pywebview — в логических пикселях, как в CSS)."""
        width, height = self._window.width, self._window.height
        self._window.resize(width, max(MIN_HEIGHT, height + delta))

    def choose_folder(self) -> str | None:
        """Диалог выбора папки."""
        result = self._window.create_file_dialog(webview.FileDialog.FOLDER)
        return str(result[0]) if result else None

    def close(self) -> None:
        """Закрывает окно."""
        self._window.destroy()


def run(settings: Settings | None = None) -> None:
    """Создаёт окно и запускает GUI-цикл (блокирует до закрытия окна)."""
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
    api._attach_window(PywebviewWindow(window))

    webview.start(gui="edgechromium", debug=settings.debug)
