"""Точка входа: ``python -m simple_pyramid`` или ``simple-pyramid``."""

import logging


def main() -> None:
    """Запуск приложения."""
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s - %(levelname)s - %(name)s - %(message)s",
        datefmt="%H:%M:%S",
    )
    from simple_pyramid.desktop.window import run  # noqa: PLC0415 — webview грузим после логов

    run()


if __name__ == "__main__":
    main()
