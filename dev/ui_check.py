"""Автопроверка интерфейса в настоящем окне pywebview: ``uv run python -m dev.ui_check``.

Поднимает эмулятор, открывает окно, выполняет сценарий (вход → поиск → ...) через
``evaluate_js`` и печатает состояние DOM после каждого шага, затем закрывает окно.
Удобно, чтобы быстро убедиться, что JS не упал и поля заполнились.
"""

import argparse
import json
import socket
import threading
import time
from typing import Any

import uvicorn
import webview

from dev.mock_server.app import create_app
from simple_pyramid.config import Settings
from simple_pyramid.desktop.bridge import APP_TITLE, Api
from simple_pyramid.desktop.credentials import CredentialStore
from simple_pyramid.desktop.emitter import WindowEmitter
from simple_pyramid.desktop.window import HEIGHT, WIDTH, PywebviewWindow, resource_path

# JS, собирающий «снимок» главного окна
SNAPSHOT_JS = """
(() => {
  const t = s => { const el = document.querySelector(s); return el ? el.innerText.trim() : null; };
  return JSON.stringify({
    title: document.title,
    status: t('#status'),
    model: t('#m-model'), address: t('#m-address'), account: t('#m-account'),
    time: t('#m-time'), readings: t('#readings tbody'),
    routes: t('#routes'),
    skeletons: document.querySelectorAll('.skeleton').length,
    busy: Array.from(document.querySelectorAll('.busy')).map(e => e.id),
    overlays: Array.from(document.querySelectorAll('.overlay.show')).map(e => e.id),
    errors: window.__errors || [],
    height: document.documentElement.scrollHeight,
  });
})()
"""

CATCH_ERRORS_JS = """
window.__errors = [];
window.addEventListener('error', e => window.__errors.push(String(e.message)));
"""


def free_port() -> int:
    """Свободный TCP-порт."""
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return int(s.getsockname()[1])


def run_scenario(window: Any, steps: list[str]) -> None:
    """Выполняет шаги сценария и печатает снимки DOM."""
    window.events.loaded.wait(15)
    window.evaluate_js(CATCH_ERRORS_JS)
    time.sleep(1)
    for step in steps:
        cmd, _, arg = step.partition(":")
        if cmd == "wait":
            time.sleep(float(arg))
        elif cmd == "js":
            window.evaluate_js(arg)
        elif cmd == "click":
            window.evaluate_js(f"document.querySelector({json.dumps(arg)}).click()")
        elif cmd == "type":
            selector, _, text = arg.partition("=")
            window.evaluate_js(
                f"(el => {{ el.value = {json.dumps(text)}; }})(document.querySelector({json.dumps(selector)}))"
            )
        elif cmd == "snap":
            snap = json.loads(window.evaluate_js(SNAPSHOT_JS))
            print(f"--- {arg or 'snapshot'}")  # noqa: T201
            print(json.dumps(snap, ensure_ascii=False, indent=1))  # noqa: T201
    window.destroy()


DEFAULT_STEPS = [
    "wait:1",
    "snap:старт",
    "type:#li-login=FilippovAS",
    "type:#li-pass=demo",
    "click:#li-ok",
    "wait:1",
    "type:#meter=021250611469",
    "click:#btn-find",
    "wait:0.3",
    "snap:загрузка",
    "wait:3",
    "snap:загружено",
]


def main() -> None:
    """Эмулятор + окно + сценарий."""
    parser = argparse.ArgumentParser(description="Автопроверка UI")
    parser.add_argument(
        "steps", nargs="*", help="шаги: wait:1 click:#sel type:#sel=текст js:код snap:имя"
    )
    args = parser.parse_args()
    port = free_port()
    mock = create_app(latency=(0.1, 0.6), task_duration=(1, 2))
    server = uvicorn.Server(uvicorn.Config(mock, host="127.0.0.1", port=port, log_level="warning"))
    threading.Thread(target=server.run, daemon=True).start()

    settings = Settings(
        api_url=f"http://127.0.0.1:{port}/api/v1", mock=True, task_poll_interval=0.3
    )
    emitter = WindowEmitter()

    class NoKeyring:
        """Хранилище «в никуда» — проверка не трогает учётки."""

        def get_password(self, *_: str) -> None:
            return None

        def set_password(self, *_: str) -> None:
            return None

        def delete_password(self, *_: str) -> None:
            return None

    api = Api(settings, emitter, credentials=CredentialStore(backend=NoKeyring()))
    window = webview.create_window(
        APP_TITLE, str(resource_path("ui/index.html")), js_api=api, width=WIDTH, height=HEIGHT
    )
    emitter.window = window
    api._attach_window(PywebviewWindow(window))
    webview.start(run_scenario, (window, args.steps or DEFAULT_STEPS), gui="edgechromium")


if __name__ == "__main__":
    main()
