"""Хранение логина и пароля в Windows Credential Manager (через keyring).

Раньше (до 1.4) пароль лежал открытым текстом в pickle-файле рядом с программой —
при первом запуске он переносится в хранилище Windows, а файл удаляется.
"""

import logging
import pickle
from pathlib import Path
from typing import Any

import keyring
from keyring.errors import KeyringError

logger = logging.getLogger(__name__)

SERVICE = "SimplePyramid"
# Учётки эмулятора хранятся отдельно и никогда не смешиваются с боевыми
MOCK_SERVICE = "SimplePyramid-Emulator"
LAST_LOGIN_KEY = "__last_login__"


class CredentialStore:
    """Сохранённые учётные данные.

    Args:
        legacy_file: путь к старому pickle-файлу для разовой миграции.
        backend: реализация keyring (по умолчанию системная) — подменяется в тестах.
        service: имя записи в хранилище Windows.
    """

    def __init__(
        self, legacy_file: Path | None = None, backend: Any = None, service: str = SERVICE
    ) -> None:
        self._legacy_file = legacy_file
        self._kr: Any = backend or keyring
        self._service = service

    def load(self) -> tuple[str, str] | None:
        """Возвращает ``(логин, пароль)`` или None, если ничего не сохранено."""
        self._migrate_legacy()
        try:
            login = self._kr.get_password(self._service, LAST_LOGIN_KEY)
            password = self._kr.get_password(self._service, login) if login else None
        except KeyringError:
            logger.exception("Не удалось прочитать учётные данные")
            return None
        if login and password:
            return login, password
        return None

    def save(self, login: str, password: str) -> None:
        """Сохраняет логин и пароль."""
        try:
            self._kr.set_password(self._service, login, password)
            self._kr.set_password(self._service, LAST_LOGIN_KEY, login)
        except KeyringError:
            logger.exception("Не удалось сохранить учётные данные")

    def clear(self) -> None:
        """Забывает сохранённого пользователя (пароль удаляется)."""
        try:
            login = self._kr.get_password(self._service, LAST_LOGIN_KEY)
            if login:
                self._kr.delete_password(self._service, login)
            self._kr.delete_password(self._service, LAST_LOGIN_KEY)
        except KeyringError:
            logger.debug("Нечего удалять из хранилища", exc_info=True)

    def _migrate_legacy(self) -> None:
        """Переносит логин/пароль из старого pickle в хранилище и удаляет файл."""
        path = self._legacy_file
        if path is None or not path.exists():
            return
        try:
            with path.open("rb") as f:
                # Файл писала сама программа — это не внешние данные
                data = pickle.load(f)  # noqa: S301
            login, password = data.get("login"), data.get("password")
            if login and password:
                self.save(login, password)
            path.unlink()
            logger.info("Учётные данные перенесены из %s в хранилище Windows", path)
        except (OSError, pickle.UnpicklingError, AttributeError, EOFError):
            logger.exception("Не удалось перенести старые учётные данные")
