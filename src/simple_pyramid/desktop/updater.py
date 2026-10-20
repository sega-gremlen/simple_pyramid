"""Проверка и загрузка обновлений.

Версия и changelog берутся из последнего GitHub Release (его текст генерирует git-cliff
из коммитов), сам установщик качается с резервного сервера — GitHub с рабочих ПК
бывает недоступен.
"""

import asyncio
import logging
from collections.abc import Callable
from pathlib import Path

import httpx
from packaging.version import InvalidVersion, Version
from pydantic import BaseModel, ConfigDict

from simple_pyramid.config import Settings
from simple_pyramid.version import __version__, is_dev_build

logger = logging.getLogger(__name__)

RETRY_PAUSE = 5.0
CHUNK_SIZE = 64 * 1024

ProgressCallback = Callable[[float, int, int], None]
StatusCallback = Callable[[str, int], None]


class ReleaseAsset(BaseModel):
    """Файл, приложенный к релизу."""

    model_config = ConfigDict(extra="ignore")

    browser_download_url: str


class GithubRelease(BaseModel):
    """Ответ GitHub API ``releases/latest`` (нужные поля)."""

    model_config = ConfigDict(extra="ignore")

    tag_name: str
    body: str | None = None
    assets: list[ReleaseAsset] = []


class UpdateInfo(BaseModel):
    """Доступное обновление."""

    version: str
    url: str | None
    changelog: str


def is_newer(latest: str, current: str) -> bool:
    """Сравнивает версии (``v1.2.3`` и ``1.2.3`` — одно и то же)."""
    try:
        return Version(latest.lstrip("v")) > Version(current.lstrip("v"))
    except InvalidVersion:
        return False


async def check_update(
    settings: Settings, *, transport: httpx.AsyncBaseTransport | None = None
) -> UpdateInfo | None:
    """Проверяет, есть ли версия новее текущей. При запуске из исходников не проверяет."""
    if is_dev_build():
        return None
    try:
        async with httpx.AsyncClient(timeout=5, transport=transport) as http:
            response = await http.get(settings.github_api)
            response.raise_for_status()
        release = GithubRelease.model_validate_json(response.content)
    except (httpx.HTTPError, ValueError):
        logger.info("Проверка обновлений не удалась", exc_info=True)
        return None
    if not is_newer(release.tag_name, __version__):
        return None
    return UpdateInfo(
        version=release.tag_name.lstrip("v"),
        url=release.assets[0].browser_download_url if release.assets else None,
        changelog=(release.body or "").strip(),
    )


async def download_update(
    settings: Settings,
    target_dir: Path,
    *,
    on_progress: ProgressCallback | None = None,
    on_status: StatusCallback | None = None,
    transport: httpx.AsyncBaseTransport | None = None,
    retry_pause: float = RETRY_PAUSE,
) -> Path:
    """Скачивает установщик, переподключаясь до успеха. Возвращает путь к файлу.

    Callbacks:
        on_status(сообщение, номер_попытки) — 0 означает «соединение установлено».
        on_progress(процент, скачано_байт, всего_байт).
    """
    url = settings.fallback_exe_url
    filename = f"{url.rsplit('/', 1)[-1].removesuffix('.exe')}_update.exe"
    path = target_dir / filename
    attempt = 1
    async with httpx.AsyncClient(verify=False, timeout=60, transport=transport) as http:
        while True:
            if on_status:
                on_status(f"Попытка {attempt}…", attempt)
            try:
                async with http.stream("GET", url) as response:
                    if response.status_code != httpx.codes.OK:
                        if on_status:
                            on_status(f"Сервер вернул {response.status_code}", attempt)
                    else:
                        if on_status:
                            on_status("Соединение установлено", 0)
                        await _save_stream(response, path, on_progress)
                        return path
            except httpx.HTTPError as exc:
                if on_status:
                    on_status(f"Ошибка: {exc}", attempt)
            attempt += 1
            await asyncio.sleep(retry_pause)


async def _save_stream(
    response: httpx.Response, path: Path, on_progress: ProgressCallback | None
) -> None:
    """Пишет тело ответа в файл, сообщая прогресс."""
    total = int(response.headers.get("content-length", 0))
    downloaded = 0
    with path.open("wb") as f:
        async for chunk in response.aiter_bytes(CHUNK_SIZE):
            f.write(chunk)
            downloaded += len(chunk)
            if on_progress:
                on_progress(downloaded / total * 100 if total else 0, downloaded, total)
    if on_progress:
        on_progress(100, downloaded, total)
