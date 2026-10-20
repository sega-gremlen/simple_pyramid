"""Асинхронный клиент API «Пирамиды» с Bearer-авторизацией.

Токен получается при входе и подставляется во все запросы. Если сервер ответил 401
(токен протух или кто-то зашёл под этим же логином с другого места), клиент один раз
перелогинивается и повторяет запрос.
"""

import asyncio
import logging
from datetime import datetime
from functools import cache
from typing import Any, Self, cast

import httpx
from pydantic import TypeAdapter, ValidationError

from simple_pyramid.api import endpoints
from simple_pyramid.api.errors import (
    ApiError,
    AuthError,
    ConnectionFailedError,
    UnexpectedResponseError,
)
from simple_pyramid.api.models.auth import LoginRequest, LoginResponse
from simple_pyramid.api.models.events import (
    EventsRequest,
    PyramidEvent,
    StartReadEventsRequest,
)
from simple_pyramid.api.models.instances import (
    GetInstanceInfoResponse,
    GetInstancesRequest,
    GetInstancesResponse,
)
from simple_pyramid.api.models.loadlimit import (
    LoadLimitPoint,
    LoadLimitStatesRequest,
    StartReadLoadLimitRequest,
)
from simple_pyramid.api.models.meterdata import AcquireRequest, MeterDataReadRequest, MeterPointData
from simple_pyramid.api.models.reports import (
    HOURLY_REPORT_FORMAT_ID,
    HOURLY_REPORT_ID,
    ArchiveReportRequest,
    ReportNode,
    ReportTask,
    build_hourly_report_payload,
)
from simple_pyramid.api.models.tasks import LOG_TYPE_FULL, BackgroundTask, TaskState
from simple_pyramid.config import Settings

logger = logging.getLogger(__name__)

# Заголовок, снимающий лимит на объём выборки (так делает веб-интерфейс)
NO_LIMIT_HEADERS = {"No-Limit": "true"}


@cache
def _adapter(tp: Any) -> TypeAdapter[Any]:
    """Кэширует TypeAdapter для типа ответа."""
    return TypeAdapter(tp)


class PyramidClient:
    """Клиент API Пирамиды.

    Args:
        settings: настройки (URL, таймауты, проверка сертификата).
        transport: подменный транспорт httpx — для тестов и эмулятора в памяти.
    """

    def __init__(
        self, settings: Settings, *, transport: httpx.AsyncBaseTransport | None = None
    ) -> None:
        self._settings = settings
        self._http = httpx.AsyncClient(
            base_url=settings.api_url.rstrip("/") + "/",
            verify=settings.verify_ssl,
            timeout=settings.request_timeout,
            transport=transport,
            headers={"Content-Type": "application/json"},
        )
        self._username: str | None = None
        self._password: str | None = None
        self._token: str | None = None
        self._token_generation = 0
        self._login_lock = asyncio.Lock()
        self.user_id: int | str | None = None

    async def __aenter__(self) -> Self:
        return self

    async def __aexit__(self, *_: object) -> None:
        await self.aclose()

    async def aclose(self) -> None:
        """Закрывает HTTP-соединения."""
        await self._http.aclose()

    # ------------------------------------------------------------ авторизация
    @property
    def username(self) -> str | None:
        """Логин, под которым выполнен (или выполняется) вход."""
        return self._username

    @property
    def authorized(self) -> bool:
        """Есть ли токен авторизации."""
        return self._token is not None

    async def login(self, username: str, password: str) -> LoginResponse:
        """Выполняет вход и запоминает логин/пароль для автоматического перелогина.

        Raises:
            AuthError: неверный логин или пароль.
            ConnectionFailedError: сервер недоступен.
        """
        payload = LoginRequest(username=username, password=password).to_payload()
        params = {"timeZoneOffset": self._settings.timezone_offset}
        try:
            response = await self._http.post(endpoints.LOGIN, json=payload, params=params)
        except httpx.TransportError as exc:
            raise ConnectionFailedError(
                "Не удалось подключиться к серверу Пирамиды", details=repr(exc)
            ) from exc
        if response.is_error:
            raise AuthError("Неверный логин или пароль", details=response.text[:2000])
        data = self._parse(response, LoginResponse)

        self._username, self._password = username, password
        self._token = data.tokens.access_token
        self._token_generation += 1
        self.user_id = data.user_id
        self._http.headers["Authorization"] = f"Bearer {self._token}"
        logger.info("Вход выполнен: %s", username)
        return data

    def logout(self) -> None:
        """Забывает токен и учётные данные (смена пользователя)."""
        self._username = self._password = self._token = None
        self.user_id = None
        self._http.headers.pop("Authorization", None)

    async def _relogin(self, seen_generation: int) -> None:
        """Перелогинивается, если с момента ``seen_generation`` этого ещё никто не сделал."""
        async with self._login_lock:
            if self._token is not None and self._token_generation != seen_generation:
                return  # параллельный запрос уже перелогинился
            if not self._username or not self._password:
                raise AuthError("Нет активной сессии — войдите заново")
            logger.info("Перелогин (токен недействителен)")
            await self.login(self._username, self._password)

    # ------------------------------------------------------------ транспорт
    async def _request(
        self,
        method: str,
        path: str,
        *,
        json: Any = None,
        params: dict[str, Any] | None = None,
        headers: dict[str, str] | None = None,
        retry_auth: bool = True,
    ) -> httpx.Response:
        """Выполняет запрос с авто-перелогином и переводом ошибок в понятные исключения."""
        generation = self._token_generation
        if self._token is None:
            await self._relogin(generation)
            generation = self._token_generation
        try:
            response = await self._http.request(
                method, path, json=json, params=params, headers=headers
            )
        except httpx.TimeoutException as exc:
            raise ConnectionFailedError("Сервер не ответил вовремя", details=repr(exc)) from exc
        except httpx.TransportError as exc:
            raise ConnectionFailedError(
                "Не удалось подключиться к серверу Пирамиды", details=repr(exc)
            ) from exc

        if response.status_code == httpx.codes.UNAUTHORIZED and retry_auth:
            await self._relogin(generation)
            return await self._request(
                method, path, json=json, params=params, headers=headers, retry_auth=False
            )
        if response.is_error:
            raise ApiError(
                response.status_code,
                f"Сервер вернул ошибку {response.status_code}",
                details=f"{method} {path}\n{response.text[:2000]}",
            )
        return response

    @staticmethod
    def _parse[T](response: httpx.Response, tp: type[T]) -> T:
        """Проверяет и разбирает JSON ответа по модели."""
        try:
            result: T = _adapter(cast("Any", tp)).validate_json(response.content)
        except ValidationError as exc:
            raise UnexpectedResponseError(
                "Сервер вернул данные в неожиданном формате",
                details=f"{response.request.method} {response.request.url}\n{exc}",
            ) from exc
        return result

    async def _call[T](
        self,
        tp: type[T],
        method: str,
        path: str,
        *,
        json: Any = None,
        params: dict[str, Any] | None = None,
        headers: dict[str, str] | None = None,
    ) -> T:
        """Запрос + разбор ответа по модели ``tp``."""
        response = await self._request(method, path, json=json, params=params, headers=headers)
        return self._parse(response, tp)

    # ------------------------------------------------------------ прибор и точка
    async def get_instances(self, meter_num: str) -> GetInstancesResponse:
        """Ищет прибор учёта по (части) заводского номера."""
        body = GetInstancesRequest.by_meter_number(meter_num).to_payload()
        return await self._call(GetInstancesResponse, "POST", endpoints.GET_INSTANCES, json=body)

    async def get_instance_info(self, point_id: int) -> GetInstanceInfoResponse:
        """Информация о точке учёта: лицевой счёт, адрес."""
        return await self._call(
            GetInstanceInfoResponse,
            "GET",
            endpoints.GET_INSTANCE_INFO,
            params={"instanceId": point_id},
        )

    # ------------------------------------------------------------ показания
    async def read_meter_data(
        self, request: MeterDataReadRequest, *, no_limit: bool = False
    ) -> list[MeterPointData]:
        """Читает показания из базы Пирамиды."""
        return await self._call(
            list[MeterPointData],
            "POST",
            endpoints.METERDATA_READ,
            json=request.to_payload(),
            headers=NO_LIMIT_HEADERS if no_limit else None,
        )

    async def start_acquire(self, request: AcquireRequest) -> int:
        """Создаёт задачу опроса прибора (сбор показаний «сейчас»). Возвращает id задачи."""
        return await self._call(
            int,
            "POST",
            endpoints.METERDATA_ACQUIRE,
            json=request.to_payload(),
            headers=NO_LIMIT_HEADERS,
        )

    # ------------------------------------------------------------ нагрузка
    async def get_load_limit_states(self, point_ids: list[int]) -> list[LoadLimitPoint]:
        """Состояние реле и лимит мощности (на момент последнего опроса)."""
        body = LoadLimitStatesRequest(instances_ids=point_ids).to_payload()
        return await self._call(
            list[LoadLimitPoint], "POST", endpoints.LOAD_LIMIT_STATES, json=body
        )

    async def start_read_load_limit(self, meter_ids: list[int]) -> int:
        """Создаёт задачу опроса реле и лимита у прибора. Принимает id ПРИБОРОВ."""
        body = StartReadLoadLimitRequest(meters_id=meter_ids).to_payload()
        return await self._call(int, "POST", endpoints.LOAD_LIMIT_START_READ, json=body)

    # ------------------------------------------------------------ события
    async def get_events(self, request: EventsRequest) -> list[PyramidEvent]:
        """Журнал событий из базы Пирамиды."""
        return await self._call(
            list[PyramidEvent], "POST", endpoints.EVENTS_GET, json=request.to_payload()
        )

    async def start_read_events(self, request: StartReadEventsRequest) -> int:
        """Создаёт задачу вычитки журнала событий с прибора."""
        return await self._call(int, "POST", endpoints.EVENTS_START_READ, json=request.to_payload())

    # ------------------------------------------------------------ фоновые задачи
    async def get_background_task(self, task_id: int) -> BackgroundTask:
        """Первый запрос состояния задачи (так делает веб-интерфейс сразу после создания)."""
        return await self._call(
            BackgroundTask,
            "GET",
            endpoints.BACKGROUND_TASK,
            params={"backgroundTaskId": task_id},
        )

    async def get_background_task_state(
        self, task_id: int, log_type: int = LOG_TYPE_FULL
    ) -> TaskState:
        """Последующие запросы состояния задачи."""
        return await self._call(
            TaskState,
            "GET",
            endpoints.BACKGROUND_TASK_STATE,
            params={"backgroundTaskId": task_id, "logType": log_type},
        )

    # ------------------------------------------------------------ отчёты
    async def create_hourly_report(
        self, start: datetime, end: datetime, nodes: list[ReportNode]
    ) -> ReportTask:
        """Создаёт задачу формирования почасового отчёта.

        Отчёт в Пирамиде: 02.01 Показания и профиль ЭЭ (30 и 60 мин) по точке учета (СРС).
        """
        return await self._call(
            ReportTask,
            "POST",
            endpoints.REPORT_CREATE,
            json=build_hourly_report_payload(start, end, nodes),
            params={"reportId": HOURLY_REPORT_ID, "reportFormatDataId": HOURLY_REPORT_FORMAT_ID},
        )

    async def download_archive_report(self, archive_entry_id: int | str) -> bytes:
        """Скачивает готовый файл отчёта из архива. Возвращает содержимое xlsx."""
        body = ArchiveReportRequest(
            user_id=self.user_id, archive_entry_id=archive_entry_id
        ).to_payload()
        response = await self._request("POST", endpoints.REPORT_ARCHIVE, json=body)
        return response.content
