"""Общие фикстуры тестов."""

import json
from collections.abc import AsyncIterator
from pathlib import Path
from typing import Any

import httpx
import pytest
from fastapi import FastAPI

from dev.mock_server.app import create_app
from simple_pyramid.api.client import PyramidClient
from simple_pyramid.config import Settings
from simple_pyramid.services.meter_service import MeterService
from simple_pyramid.services.sink import RecordingSink

# Путь к папке с данными (относительно этого файла)
DATA_DIR = Path(__file__).parent / "data"


def load_json(filename: str) -> Any:
    """Загружает JSON-файл из папки data."""
    return json.loads((DATA_DIR / filename).read_text(encoding="utf-8"))


@pytest.fixture
def data() -> Any:
    """Функция-загрузчик тестовых JSON: ``data("instances.json")``."""
    return load_json


@pytest.fixture
def settings(tmp_path: Path) -> Settings:
    """Настройки для тестов: эмулятор в памяти, быстрые опросы задач."""
    return Settings(
        api_url="http://pyramid.test/api/v1",
        task_poll_interval=0.01,
        task_timeout=5,
        ping_attempts=3,
        data_dir=tmp_path,
        legacy_creds_file=tmp_path / "pyramid_creds.pkl",
        _env_file=None,  # type: ignore[call-arg]
    )


@pytest.fixture
def mock_app() -> FastAPI:
    """Эмулятор Пирамиды без задержек и с мгновенными задачами."""
    return create_app(latency=(0, 0), task_duration=(0, 0))


@pytest.fixture
async def client(settings: Settings, mock_app: FastAPI) -> AsyncIterator[PyramidClient]:
    """Клиент, подключённый к эмулятору в памяти, уже залогиненный."""
    transport = httpx.ASGITransport(app=mock_app)
    async with PyramidClient(settings, transport=transport) as c:
        await c.login("tester", "secret")
        yield c


@pytest.fixture
def sink() -> RecordingSink:
    """Sink, копящий события для проверки."""
    return RecordingSink()


@pytest.fixture
def service(client: PyramidClient, settings: Settings, sink: RecordingSink) -> MeterService:
    """Сервис поверх эмулятора."""
    return MeterService(client, settings, sink)
