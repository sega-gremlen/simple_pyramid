"""Мост JS ↔ Python: методы этого класса вызываются из ``ui`` как ``pywebview.api.<метод>``.

Правила:
* публичные методы — только то, что зовёт JS; всё остальное — с подчёркиванием
  (pywebview выставляет в JS все публичные атрибуты);
* долгие операции не блокируют: ставим корутину в :class:`AsyncRunner` и сразу выходим,
  результат приходит в JS событиями ``window.on<Event>``;
* короткие запрос-ответ операции (страница событий, подневка) возвращают значение —
  в JS это Promise.
"""

import asyncio
import logging
import os
import subprocess
import sys
from collections.abc import Callable, Coroutine
from concurrent.futures import Future
from pathlib import Path
from typing import Any, Protocol

from simple_pyramid.api.client import PyramidClient
from simple_pyramid.api.errors import AuthError, PyramidError
from simple_pyramid.config import Settings
from simple_pyramid.desktop.credentials import MOCK_SERVICE, CredentialStore
from simple_pyramid.desktop.pinger import ping_until_success
from simple_pyramid.desktop.runner import AsyncRunner
from simple_pyramid.desktop.updater import (
    SeenVersionStore,
    UpdateInfo,
    check_update,
    download_update,
    whats_new,
)
from simple_pyramid.domain.period import parse_period
from simple_pyramid.services.meter_service import MeterService, MeterSession
from simple_pyramid.services.sink import Section, Sink, StatusKind
from simple_pyramid.version import display_version

logger = logging.getLogger(__name__)

APP_TITLE = "Простая Пирамида"
EVENTS_PAGE_LIMIT_MAX = 100
REFRESHABLE = {Section.READINGS.value, Section.LOAD.value, Section.EVENTS.value}
# Задачи, относящиеся к открытому прибору (отменяются при новом поиске)
METER_TASK_PREFIXES = ("search", "ping:", "refresh:")


class WindowControl(Protocol):
    """Операции с окном, нужные мосту (реализация — ``desktop.window``)."""

    def set_title(self, title: str) -> None:
        """Меняет заголовок окна."""

    def grow_height(self, delta: int) -> None:
        """Меняет высоту окна на ``delta`` CSS-пикселей."""

    def choose_folder(self) -> str | None:
        """Диалог выбора папки."""

    def close(self) -> None:
        """Закрывает окно."""


def short_login(login: str | None) -> str | None:
    r"""Логин без домена: ``samara.vlmrk.corp\FilippovAS`` → ``FilippovAS``."""
    if not login:
        return None
    return login.replace("/", "\\").rsplit("\\", 1)[-1]


def window_title(login: str | None, *, mock: bool) -> str:
    """Заголовок окна: «Простая Пирамида • FilippovAS» (+ пометка эмулятора)."""
    parts = [APP_TITLE]
    if login:
        parts.append(short_login(login) or login)
    if mock:
        parts.append("ЭМУЛЯТОР")
    return " • ".join(parts)


def open_in_explorer(path: str) -> None:
    """Открывает папку (или папку файла) в проводнике."""
    target = Path(path)
    folder = target if target.is_dir() else target.parent
    if sys.platform == "win32":
        os.startfile(folder)  # noqa: S606 — открываем папку, которую выбрал пользователь
    else:
        subprocess.Popen(["xdg-open", str(folder)])  # noqa: S603, S607


class Api:
    """Методы, доступные из JS."""

    def __init__(
        self,
        settings: Settings,
        sink: Sink,
        *,
        runner: AsyncRunner | None = None,
        client: PyramidClient | None = None,
        credentials: CredentialStore | None = None,
    ) -> None:
        self._settings = settings
        self._sink = sink
        self._runner = runner or AsyncRunner()
        self._client = client or PyramidClient(settings)
        self._service = MeterService(self._client, settings, sink)
        self._creds = credentials or (
            CredentialStore(service=MOCK_SERVICE)
            if settings.mock
            else CredentialStore(settings.legacy_creds_file)
        )
        self._window: WindowControl | None = None
        self._session: MeterSession | None = None
        self._tasks: dict[str, Future[Any]] = {}
        self._update: UpdateInfo | None = None

    # ------------------------------------------------------------ служебное
    def _attach_window(self, window: WindowControl) -> None:
        """Подключает окно (до его показа: заголовок задаётся при создании окна)."""
        self._window = window

    def _update_title(self) -> None:
        """Обновляет заголовок окна под текущего пользователя."""
        if self._window:
            title = window_title(self._client.username, mock=self._settings.mock)
            self._window.set_title(title)

    def _status(self, text: str, kind: StatusKind = StatusKind.INFO) -> None:
        """Сообщение в статус-строку."""
        self._sink.emit("Status", {"text": text, "kind": kind.value})

    def _error(self, exc: BaseException, *, title: str | None = None) -> None:
        """Показывает ошибку модальным окном."""
        if isinstance(exc, PyramidError):
            payload = {
                "title": title or exc.title,
                "message": str(exc),
                "details": exc.details,
            }
        else:
            logger.error("Необработанная ошибка", exc_info=exc)
            payload = {
                "title": title or "Внутренняя ошибка",
                "message": "Что-то пошло не так. Подробности — ниже.",
                "details": f"{type(exc).__name__}: {exc}",
            }
        self._sink.emit("Error", payload)

    def _spawn(
        self,
        key: str,
        coro: Coroutine[Any, Any, Any],
        *,
        on_error: Callable[[BaseException], None] | None = None,
    ) -> Future[Any]:
        """Запускает корутину под ключом ``key``; предыдущая с тем же ключом отменяется."""
        self._cancel(key)
        future = self._runner.submit(coro)
        self._tasks[key] = future

        def done(f: Future[Any]) -> None:
            if self._tasks.get(key) is f:
                del self._tasks[key]
            if f.cancelled():
                return
            exc = f.exception()
            if exc is not None:
                (on_error or self._error)(exc)

        future.add_done_callback(done)
        return future

    def _cancel(self, key: str) -> bool:
        """Отменяет задачу ``key``, если она идёт."""
        future = self._tasks.pop(key, None)
        if future and not future.done():
            future.cancel()
            return True
        return False

    def _cancel_prefix(self, *prefixes: str) -> None:
        """Отменяет все задачи с ключом, начинающимся на один из ``prefixes``."""
        for key in [k for k in self._tasks if k.startswith(prefixes)]:
            self._cancel(key)

    # ------------------------------------------------------------ старт и вход
    def bootstrap(self) -> dict[str, Any]:
        """Первый вызов из JS: версия и попытка автовхода по сохранённым данным."""
        self._spawn("update-check", self._check_update(), on_error=lambda _: None)
        self._spawn("whats-new", self._whats_new(), on_error=lambda _: None)
        saved = self._creds.load()
        info = {"version": display_version(), "mock": self._settings.mock}
        if saved:
            login, password = saved
            self._spawn("login", self._login(login, password, remember=False))
            return {**info, "state": "logging_in", "login": short_login(login)}
        return {**info, "state": "need_login"}

    def login(self, login: str, password: str, remember: bool = True) -> None:
        """Вход по введённым логину и паролю."""
        self._spawn("login", self._login(login.strip(), password, remember=remember))

    async def _login(self, login: str, password: str, *, remember: bool) -> None:
        """Сценарий входа."""
        self._status("Выполняется вход…")
        try:
            await self._client.login(login, password)
        except PyramidError as exc:
            self._sink.emit("Auth", {"ok": False, "error": str(exc)})
            self._status(str(exc), StatusKind.ERR)
            return
        if remember:
            await asyncio.to_thread(self._creds.save, login, password)
        self._update_title()
        self._sink.emit("Auth", {"ok": True, "login": short_login(login)})
        self._status(f"Вход выполнен: {short_login(login)}", StatusKind.OK)

    def logout(self) -> None:
        """Смена пользователя: забыть сохранённые данные и показать окно входа."""
        self._cancel_prefix("")
        self._client.logout()
        self._session = None
        self._creds.clear()
        self._update_title()
        self._sink.emit("Auth", {"ok": False, "error": ""})

    # ------------------------------------------------------------ поиск прибора
    def search(self, meter_num: str) -> None:
        """Найти прибор и загрузить все его данные (потоково)."""
        meter_num = meter_num.strip()
        if not meter_num:
            self._status("Введите номер ПУ", StatusKind.WARN)
            return
        # Новый поиск отменяет всё, что относилось к предыдущему прибору
        self._cancel_prefix(*METER_TASK_PREFIXES)
        self._session = None
        self._sink.emit("SearchStarted", {"meterNum": meter_num})
        self._spawn("search", self._search(meter_num), on_error=self._search_failed)

    async def _search(self, meter_num: str) -> None:
        """Сценарий поиска."""
        if not self._client.authorized and not self._client.username:
            raise AuthError("Нет активной сессии — войдите заново")
        session = await self._service.find(meter_num)
        self._session = session
        for route in session.identity.routes:
            self.ping(route.id)
        await self._service.load_details(session)

    def _search_failed(self, exc: BaseException) -> None:
        """Прибор не найден — это не авария: пишем в статус и очищаем экран."""
        self._sink.emit("SearchFailed", {"message": str(exc)})
        if isinstance(exc, PyramidError) and exc.title.startswith(("Прибор", "Найдено")):
            self._status(str(exc).replace("\n", " "), StatusKind.WARN)
        else:
            self._error(exc)

    # ------------------------------------------------------------ пинг
    def ping(self, route_id: str) -> None:
        """(Пере)запустить пинг маршрута."""
        session = self._session
        if session is None:
            return
        route = next((r for r in session.identity.routes if r.id == route_id), None)
        if route is None:
            return
        if not route.ip:
            self._sink.emit("Ping", {"id": route_id, "state": "err", "text": "нет IP"})
            return
        self._spawn(f"ping:{route_id}", self._ping(route_id, route.ip))

    async def _ping(self, route_id: str, ip: str) -> None:
        """Пингует маршрут до первого ответа."""

        def on_attempt(attempt: int, total: int) -> None:
            self._sink.emit("Ping", {"id": route_id, "state": "wait", "text": f"{attempt}/{total}"})

        self._sink.emit("Ping", {"id": route_id, "state": "wait", "text": "…"})
        ok_attempt = await ping_until_success(
            ip, max_attempts=self._settings.ping_attempts, on_attempt=on_attempt
        )
        if ok_attempt:
            self._sink.emit("Ping", {"id": route_id, "state": "ok", "text": "в сети"})
            self._status(f"{ip}: в сети (с {ok_attempt}-й попытки)", StatusKind.OK)
        else:
            self._sink.emit("Ping", {"id": route_id, "state": "err", "text": "нет ответа"})
            self._status(f"{ip}: нет ответа", StatusKind.WARN)

    # ------------------------------------------------------------ обновление блоков
    def refresh(self, section: str) -> bool:
        """Опросить прибор и обновить блок ``readings`` / ``load`` / ``events``."""
        session = self._session
        if session is None or section not in REFRESHABLE:
            return False
        handlers = {
            Section.READINGS.value: self._service.refresh_readings,
            Section.LOAD.value: self._service.refresh_load,
            Section.EVENTS.value: self._service.refresh_events,
        }
        self._spawn(f"refresh:{section}", handlers[section](session))
        return True

    def cancel(self, section: str) -> bool:
        """Прервать обновление блока: остаются прежние значения."""
        return self._cancel(f"refresh:{section}")

    # ------------------------------------------------------------ события
    def events_page(self, offset: int, limit: int, important_only: bool) -> dict[str, Any]:
        """Порция событий для окна «События»."""
        if self._session is None:
            return {"items": [], "total": 0, "offset": 0, "hasMore": False}
        page = self._service.events_page(
            self._session,
            offset=int(offset),
            limit=max(1, min(int(limit), EVENTS_PAGE_LIMIT_MAX)),
            important_only=bool(important_only),
        )
        return page.to_js()

    # ------------------------------------------------------------ подневка и выгрузки
    def validate_period(self, start: str, end: str) -> dict[str, Any]:
        """Проверка периода (дублирует проверку в JS)."""
        try:
            period = parse_period(start, end)
        except ValueError as exc:
            return {"ok": False, "error": str(exc)}
        return {"ok": True, "days": period.days}

    def daily_view(self, start: str, end: str) -> dict[str, Any]:
        """Подневка для просмотра в программе."""
        session = self._session
        if session is None:
            return {"ok": False, "error": "Сначала найдите прибор"}
        try:
            period = parse_period(start, end)
        except ValueError as exc:
            return {"ok": False, "error": str(exc)}
        try:
            rows = self._runner.run(self._service.daily_rows(session, period.start, period.end))
        except PyramidError as exc:
            return {"ok": False, "error": str(exc), "details": exc.details}
        return {"ok": True, "rows": [r.to_js() for r in rows]}

    def browse_folder(self) -> str | None:
        """Диалог выбора папки для выгрузки."""
        return self._window.choose_folder() if self._window else None

    def export(self, kind: str, start: str, end: str, output_dir: str) -> dict[str, Any]:
        """Выгрузка подневки (``daily``) или почасовки (``hourly``) в xlsx."""
        session = self._session
        if session is None:
            return {"ok": False, "error": "Сначала найдите прибор"}
        try:
            period = parse_period(start, end)
        except ValueError as exc:
            return {"ok": False, "error": str(exc)}
        folder = Path(output_dir.strip())
        if not output_dir.strip() or not folder.is_dir():
            return {"ok": False, "error": "Такой папки нет"}
        self._spawn("export", self._export(kind, session, period.start, period.end, folder),
                    on_error=self._export_failed)  # fmt: skip
        return {"ok": True}

    async def _export(
        self, kind: str, session: MeterSession, start: Any, end: Any, folder: Path
    ) -> None:
        """Сценарий выгрузки."""
        self._sink.emit("Export", {"stage": "running", "kind": kind})
        if kind == "daily":
            path = await self._service.export_daily(session, start, end, folder)
        else:
            path = await self._service.export_hourly(session, start, end, folder)
        self._sink.emit("Export", {"stage": "done", "path": str(path)})
        self._status(f"Отчёт сохранён: {path.name}", StatusKind.OK)

    def _export_failed(self, exc: BaseException) -> None:
        """Выгрузка не удалась."""
        self._sink.emit("Export", {"stage": "error", "error": str(exc)})
        self._error(exc, title="Выгрузка не удалась")

    def open_folder(self, path: str) -> None:
        """Открыть папку с отчётом."""
        open_in_explorer(path)

    # ------------------------------------------------------------ окно
    def fit_height(self, delta: int) -> None:
        """Подогнать высоту окна под содержимое (``delta`` — CSS-пиксели)."""
        if self._window and abs(int(delta)) > 1:
            self._window.grow_height(int(delta))

    def close(self) -> None:
        """Закрыть программу."""
        self._cancel_prefix("")
        if self._window:
            self._window.close()

    # ------------------------------------------------------------ обновление программы
    async def _check_update(self) -> None:
        """Фоновая проверка обновлений при старте."""
        info = await check_update(self._settings)
        if info:
            self._update = info
            self._sink.emit("Update", info.model_dump())

    async def _whats_new(self) -> None:
        """Первый запуск новой версии — показать, что в ней нового."""
        info = await whats_new(self._settings, SeenVersionStore(self._settings.data_dir))
        if info:
            self._sink.emit("WhatsNew", info.model_dump())

    def start_update(self) -> None:
        """Скачать и запустить установщик новой версии."""
        self._spawn("update", self._download_update(), on_error=self._update_failed)

    async def _download_update(self) -> None:
        """Сценарий обновления."""

        def on_progress(percent: float, downloaded: int, total: int) -> None:
            self._sink.emit(
                "UpdateProgress",
                {"percent": round(percent), "downloaded": downloaded, "total": total},
            )

        def on_status(message: str, attempt: int) -> None:
            self._sink.emit("UpdateStatus", {"message": message, "attempt": attempt})

        path = await download_update(
            self._settings, Path.cwd(), on_progress=on_progress, on_status=on_status
        )
        # Запускаем установщик, скачанный с нашего сервера
        await asyncio.to_thread(subprocess.Popen, [str(path)])
        self.close()

    def _update_failed(self, exc: BaseException) -> None:
        """Обновление не скачалось."""
        self._sink.emit("UpdateStatus", {"message": f"Не удалось загрузить: {exc}", "attempt": -1})
