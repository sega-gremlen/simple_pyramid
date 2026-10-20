"""Запуск приложения вместе с эмулятором Пирамиды: ``uv run python -m dev.run``.

Эмулятор поднимается в этом же процессе на 127.0.0.1:8765, приложение смотрит на него.
Флаг ``--fast`` — без сетевых задержек и с быстрыми фоновыми задачами.
"""

import argparse
import logging
import threading

import uvicorn

from dev.mock_server.app import create_app
from simple_pyramid.config import Settings
from simple_pyramid.desktop.window import run


def start_mock(port: int, *, fast: bool) -> None:
    """Поднимает эмулятор в фоновом потоке."""
    app = create_app(latency=(0, 0), task_duration=(1, 2)) if fast else create_app()
    config = uvicorn.Config(app, host="127.0.0.1", port=port, log_level="warning")
    server = uvicorn.Server(config)
    threading.Thread(target=server.run, name="mock-pyramid", daemon=True).start()


def main() -> None:
    """Эмулятор + приложение."""
    parser = argparse.ArgumentParser(description="Приложение + эмулятор Пирамиды")
    parser.add_argument("--port", type=int, default=8765)
    parser.add_argument("--fast", action="store_true")
    parser.add_argument("--debug", action="store_true", help="открыть DevTools")
    args = parser.parse_args()
    logging.basicConfig(
        level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s"
    )
    start_mock(args.port, fast=args.fast)
    settings = Settings(
        api_url=f"http://127.0.0.1:{args.port}/api/v1",
        mock=True,
        debug=args.debug,
        task_poll_interval=0.5,
        ping_attempts=5,
    )
    run(settings)


if __name__ == "__main__":
    main()
