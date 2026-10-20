"""Версия приложения.

В репозитории всегда лежит ``0.0.0.dev0``: настоящую версию вписывает CI при релизе
(её вычисляет git-cliff по Conventional Commits). Руками не менять.
"""

import subprocess
from functools import cache
from pathlib import Path

__version__ = "0.0.0.dev0"

DEV_VERSION = "0.0.0.dev0"


def is_dev_build() -> bool:
    """Возвращает True, если программа запущена из исходников, а не из релизной сборки."""
    return __version__ == DEV_VERSION


@cache
def display_version() -> str:
    """Версия для показа пользователю.

    В релизной сборке это ``__version__``, при запуске из исходников —
    ``git describe`` (например ``1.3.1-12-gabc1234``) с пометкой ``dev``.
    """
    if not is_dev_build():
        return __version__
    repo_root = Path(__file__).resolve().parents[2]
    try:
        described = subprocess.run(
            ["git", "describe", "--tags", "--always"],  # noqa: S607 — git из PATH
            cwd=repo_root,
            capture_output=True,
            text=True,
            timeout=3,
            check=True,
        ).stdout.strip()
    except (OSError, subprocess.SubprocessError):
        return "dev"
    return f"{described.lstrip('v')}-dev"
