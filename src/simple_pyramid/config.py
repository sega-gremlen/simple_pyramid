"""Настройки приложения (pydantic-settings).

Значения берутся из переменных окружения с префиксом ``PYRAMID_`` или из файла ``.env``
в рабочей папке. Пример: ``PYRAMID_API_URL=http://127.0.0.1:8765/api/v1`` — работа
с эмулятором вместо боевого сервера.
"""

import os
import sys
from pathlib import Path

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

PROD_API_URL = "https://s00-pml-web1.hq.vlmrk.corp:8080/api/v1"


def _default_data_dir() -> Path:
    """Папка для данных пользователя (%LOCALAPPDATA%/SimplePyramid)."""
    base = os.environ.get("LOCALAPPDATA") or str(Path.home())
    return Path(base) / "SimplePyramid"


def _legacy_creds_file() -> Path:
    """Где старые версии (до 1.4) хранили pickle с логином и паролем."""
    base = getattr(sys, "_MEIPASS", None)
    if base:
        return Path(base) / "pyramid_creds.pkl"
    return Path(__file__).resolve().parents[2] / "pyramid_creds.pkl"


class Settings(BaseSettings):
    """Все настройки программы в одном месте."""

    model_config = SettingsConfigDict(
        env_prefix="PYRAMID_",
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # Сервер «Пирамиды» (PYRAMID_API_URL). Старая переменная PYRAMID_ROOT_API_URL из .env
    # намеренно НЕ читается — раньше она ни на что не влияла, и пусть так и остаётся.
    api_url: str = PROD_API_URL
    # У корпоративного сервера самоподписанный сертификат
    verify_ssl: bool = False
    timezone_offset: int = -240
    request_timeout: float = 60.0

    # Фоновые задачи (опрос прибора, отчёты)
    task_poll_interval: float = 1.0
    task_timeout: float = 15 * 60

    # Пинг маршрутов
    ping_attempts: int = 50

    # Сколько лет истории событий грузить при открытии ПУ.
    # TODO: привязать начало интервала к дате ввода точки/ПУ (кандидат — поле -1498 в getinstances)
    events_history_years: int = 10

    # Обновления
    github_api: str = "https://api.github.com/repos/sega-gremlen/simple_pyramid/releases/latest"
    fallback_exe_url: str = "https://releases.sega-gremlen.top/simple_pyramid.exe"

    # Отладка: PYRAMID_DEBUG=1 включает DevTools в окне
    debug: bool = False
    # Работа с эмулятором: в заголовке окна будет пометка «ЭМУЛЯТОР»
    mock: bool = False

    data_dir: Path = Field(default_factory=_default_data_dir)
    legacy_creds_file: Path = Field(default_factory=_legacy_creds_file)


def get_settings() -> Settings:
    """Создаёт объект настроек (читает окружение и .env)."""
    return Settings()
