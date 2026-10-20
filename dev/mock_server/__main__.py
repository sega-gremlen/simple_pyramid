"""Запуск эмулятора: ``uv run python -m dev.mock_server [--port 8765] [--fast]``."""

import argparse

import uvicorn

from dev.mock_server.app import create_app


def main() -> None:
    """Поднимает эмулятор на localhost."""
    parser = argparse.ArgumentParser(description="Эмулятор API Пирамиды")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8765)
    parser.add_argument("--fast", action="store_true", help="без задержек и с быстрыми задачами")
    args = parser.parse_args()
    app = create_app(latency=(0, 0), task_duration=(1, 2)) if args.fast else create_app()
    uvicorn.run(app, host=args.host, port=args.port, log_level="info")


if __name__ == "__main__":
    main()
