"""Интерфейс в обычном браузере (для отладки и скриншотов): ``uv run python -m dev.web_preview``.

Тот же ``ui/``, тот же Python-мост ``Api`` и эмулятор Пирамиды — только вместо pywebview
вызовы ``pywebview.api.*`` идут по HTTP, а события ``window.on*`` — через Server-Sent Events.
Открыть: http://127.0.0.1:8770/
"""

import argparse
import asyncio
import json
import logging
import tempfile
import threading
from collections.abc import AsyncIterator
from pathlib import Path
from typing import Any

import uvicorn
from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse, JSONResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles

from dev.mock_server.app import create_app as create_mock
from simple_pyramid.config import Settings
from simple_pyramid.desktop.bridge import Api

UI_DIR = Path(__file__).resolve().parents[1] / "src" / "simple_pyramid" / "ui"

SHIM = """
<script>
// Подмена pywebview для браузера: вызовы API — POST /bridge/<метод>, события — SSE.
window.pywebview = {api: new Proxy({}, {get: (_, name) => async (...args) => {
  const r = await fetch('/bridge/' + name, {method: 'POST', body: JSON.stringify(args)});
  return r.json();
}})};
const es = new EventSource('/events');
es.onmessage = m => { const {event, payload} = JSON.parse(m.data);
  if (event === '__title') { document.title = payload; return; }
  const fn = window['on' + event]; if (fn) fn(payload); };
es.onopen = () => { window.dispatchEvent(new Event('pywebviewready')); runSteps(); };

// Сценарий из URL для скриншотов: ?steps=login|search:0212|wait:2000|click:#btn|js:код
async function runSteps(){
  const steps = new URLSearchParams(location.search).get('steps');
  if (!steps) return;
  const sleep = ms => new Promise(r => setTimeout(r, ms));
  await sleep(300);
  for (const step of steps.split('|')){
    const [cmd, ...rest] = step.split(':'); const arg = rest.join(':');
    if (cmd === 'login') await window.pywebview.api.login(arg || 'FilippovAS', 'demo', false);
    if (cmd === 'search') window.pywebview.api.search(arg);
    if (cmd === 'wait') await sleep(Number(arg));
    if (cmd === 'click') document.querySelector(arg)?.click();
    if (cmd === 'hover') document.querySelector(arg)?.dispatchEvent(new MouseEvent('mouseover', {bubbles: true}));
    if (cmd === 'js') eval(arg);
  }
}
</script>
"""


class SseSink:
    """Sink, рассылающий события подключённым браузерам."""

    def __init__(self) -> None:
        self._queues: list[tuple[asyncio.AbstractEventLoop, asyncio.Queue[str]]] = []
        self._lock = threading.Lock()

    def subscribe(self) -> asyncio.Queue[str]:
        """Новая очередь для SSE-подписчика."""
        queue: asyncio.Queue[str] = asyncio.Queue()
        with self._lock:
            self._queues.append((asyncio.get_running_loop(), queue))
        return queue

    def unsubscribe(self, queue: asyncio.Queue[str]) -> None:
        """Убирает подписчика."""
        with self._lock:
            self._queues = [(loop, q) for loop, q in self._queues if q is not queue]

    def emit(self, event: str, payload: Any = None) -> None:
        """Отправляет событие всем подписчикам (из любого потока)."""
        data = json.dumps({"event": event, "payload": payload}, ensure_ascii=False, default=str)
        with self._lock:
            targets = list(self._queues)
        for loop, queue in targets:
            loop.call_soon_threadsafe(queue.put_nowait, data)


class BrowserWindow:
    """Заглушка окна: заголовок уходит в document.title, остальное — no-op."""

    def __init__(self, sink: SseSink) -> None:
        self._sink = sink
        self.folder = tempfile.mkdtemp(prefix="pyramid-export-")

    def set_title(self, title: str) -> None:
        """Заголовок вкладки браузера."""
        self._sink.emit("__title", title)

    def grow_height(self, delta: int) -> None:
        """Высоту вкладки браузера менять нельзя — только логируем."""
        logging.getLogger(__name__).info("fit_height(%s)", delta)

    def choose_folder(self, kind: str | None = None) -> str | None:
        """Вместо диалога — временная папка."""
        return self.folder

    def open_child(self, kind: str, title: str) -> None:
        """Доп. окна в браузере не открываются — только логируем (открыть /daily.html вручную)."""
        logging.getLogger(__name__).info("open_child(%s, %s)", kind, title)

    def set_child_title(self, kind: str, title: str) -> None:
        """Нечего обновлять."""

    def close(self) -> None:
        """Закрывать нечего."""


def build_app(mock_port: int) -> FastAPI:
    """Приложение предпросмотра: статика UI + мост + SSE."""
    sink = SseSink()
    settings = Settings(
        api_url=f"http://127.0.0.1:{mock_port}/api/v1", mock=True,
        task_poll_interval=0.5, ping_attempts=5,
    )  # fmt: skip
    bridge = Api(settings, sink)
    bridge._attach_window(BrowserWindow(sink))

    app = FastAPI()

    def page(name: str) -> str:
        html = (UI_DIR / name).read_text(encoding="utf-8")
        return html.replace('<script src="js/core.js">', SHIM + '<script src="js/core.js">', 1)

    @app.get("/", response_class=HTMLResponse)
    async def index() -> str:
        return page("index.html")

    @app.get("/daily.html", response_class=HTMLResponse)
    async def daily() -> str:
        return page("daily.html")

    @app.get("/events.html", response_class=HTMLResponse)
    async def events_page() -> str:
        return page("events.html")

    @app.post("/bridge/{method}")
    async def call(method: str, request: Request) -> JSONResponse:
        if method.startswith("_"):
            return JSONResponse({"error": "forbidden"}, status_code=403)
        args = json.loads(await request.body() or b"[]")
        result = await asyncio.to_thread(getattr(bridge, method), *args)
        return JSONResponse(result)

    @app.get("/events")
    async def events() -> StreamingResponse:
        queue = sink.subscribe()

        async def stream() -> AsyncIterator[str]:
            try:
                while True:
                    yield f"data: {await queue.get()}\n\n"
            finally:
                sink.unsubscribe(queue)

        return StreamingResponse(stream(), media_type="text/event-stream")

    app.mount("/", StaticFiles(directory=UI_DIR), name="ui")
    return app


def main() -> None:
    """Эмулятор + веб-предпросмотр."""
    parser = argparse.ArgumentParser(description="UI в браузере + эмулятор Пирамиды")
    parser.add_argument("--port", type=int, default=8770)
    parser.add_argument("--mock-port", type=int, default=8765)
    parser.add_argument("--fast", action="store_true")
    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO)

    mock = create_mock(latency=(0, 0), task_duration=(1, 2)) if args.fast else create_mock()
    mock_server = uvicorn.Server(
        uvicorn.Config(mock, host="127.0.0.1", port=args.mock_port, log_level="warning")
    )
    threading.Thread(target=mock_server.run, daemon=True).start()
    uvicorn.run(build_app(args.mock_port), host="127.0.0.1", port=args.port, log_level="warning")


if __name__ == "__main__":
    main()
