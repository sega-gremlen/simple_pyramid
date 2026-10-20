"""Сценарии работы с прибором: поиск, потоковая загрузка блоков, обновление, выгрузки.

Загрузка «по мере поступления»: после поиска прибора блоки (точка учёта, показания,
нагрузка, события) запрашиваются параллельно, и каждый уходит в интерфейс сразу,
как только пришёл ответ.
"""

import asyncio
import logging
import time
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Any

from simple_pyramid.api.client import PyramidClient
from simple_pyramid.api.errors import PyramidError
from simple_pyramid.api.models.events import EventsRequest, Interval, StartReadEventsRequest
from simple_pyramid.api.models.meterdata import (
    CURRENT_PARAMETERS,
    CURRENT_SOURCES,
    DAILY_PARAMETERS,
    DAILY_SOURCES,
    AcquireRequest,
    MeterDataReadRequest,
    MeterPointData,
)
from simple_pyramid.api.models.reports import ReportNode
from simple_pyramid.api.models.tasks import LogEntry, TaskState
from simple_pyramid.api.tasks import wait_for_task
from simple_pyramid.config import Settings
from simple_pyramid.domain.daily import build_daily_rows
from simple_pyramid.domain.events import alarm_summary, events_page, to_meter_events
from simple_pyramid.domain.load import build_load_info
from simple_pyramid.domain.meter import build_identity, build_point_info
from simple_pyramid.domain.models import (
    DailyRow,
    EventsPage,
    LoadInfo,
    MeterEvent,
    MeterIdentity,
    PointInfo,
    Readings,
)
from simple_pyramid.domain.readings import build_readings
from simple_pyramid.services.sink import Section, Sink, StatusKind
from simple_pyramid.services.xlsx_export import create_daily_workbook

logger = logging.getLogger(__name__)

# Отчёт формируется задачей с «кратким» логом (так было в старой версии)
REPORT_LOG_TYPE = 1


def fmt_dt(value: datetime | None) -> str:
    """Дата для сообщений: ``20.10.2026 06:45``."""
    return value.strftime("%d.%m.%Y %H:%M") if value else "—"


def _seconds(value: float) -> str:
    """``0.42`` → ``0,4 с``."""
    return f"{value:.1f} с".replace(".", ",")


def _day_start(value: date) -> datetime:
    """Полночь указанного дня."""
    return datetime(value.year, value.month, value.day)


def _safe_filename(name: str) -> str:
    """Убирает символы, недопустимые в имени файла Windows."""
    return "".join("_" if ch in '<>:"/\\|?*' else ch for ch in name).strip()


@dataclass
class MeterSession:
    """Всё, что известно о текущем открытом приборе."""

    identity: MeterIdentity
    info: PointInfo | None = None
    readings: Readings | None = None
    load: LoadInfo | None = None
    events: list[MeterEvent] | None = None
    started_at: float = field(default_factory=time.perf_counter)


class MeterService:
    """Сценарии работы с прибором.

    Args:
        client: клиент API.
        settings: настройки (интервалы опроса задач, глубина истории событий).
        sink: куда отправлять события для интерфейса.
    """

    def __init__(self, client: PyramidClient, settings: Settings, sink: Sink) -> None:
        self._client = client
        self._settings = settings
        self._sink = sink

    # ------------------------------------------------------------ вспомогательное
    def _status(self, text: str, kind: StatusKind = StatusKind.INFO) -> None:
        """Сообщение в статус-строку."""
        self._sink.emit("Status", {"text": text, "kind": kind.value})

    def _part(self, section: Section, data: Any = None, error: str | None = None) -> None:
        """Отправляет готовый блок данных (или ошибку его загрузки)."""
        self._sink.emit("MeterPart", {"section": section.value, "data": data, "error": error})

    def _busy(self, section: Section, *, busy: bool) -> None:
        """Сообщает, что блок обновляется (мерцает) или закончил."""
        self._sink.emit("SectionBusy", {"section": section.value, "busy": busy})

    async def _wait(self, task_id: int, section: Section, *, log_type: int = 2) -> TaskState:
        """Ждёт фоновую задачу, пересылая её лог в интерфейс."""

        def on_log(entry: LogEntry) -> None:
            self._sink.emit("TaskLog", {"section": section.value, "text": entry.message})

        return await wait_for_task(
            self._client,
            task_id,
            interval=self._settings.task_poll_interval,
            max_wait=self._settings.task_timeout,
            on_log=on_log,
            log_type=log_type,
        )

    async def _guarded(
        self, section: Section, loader: Callable[[], Awaitable[dict[str, Any]]]
    ) -> None:
        """Грузит блок; ошибка одного блока не мешает остальным."""
        try:
            data = await loader()
        except PyramidError as exc:
            logger.warning("Блок %s: %s", section, exc)
            self._part(section, error=str(exc))
        except Exception:
            logger.exception("Блок %s: необработанная ошибка", section)
            self._part(section, error="Внутренняя ошибка программы")
        else:
            self._part(section, data)

    # ------------------------------------------------------------ поиск и загрузка
    async def find(self, meter_num: str) -> MeterSession:
        """Ищет прибор и сразу отправляет в интерфейс тип и маршруты.

        Raises:
            MeterNotFoundError, AmbiguousMeterError: прибор не найден / найдено несколько.
        """
        started = time.perf_counter()
        identity = build_identity(meter_num, await self._client.get_instances(meter_num))
        session = MeterSession(identity=identity, started_at=started)
        self._part(Section.IDENTITY, identity.to_js())
        self._status(
            f"ПУ {identity.model or ''} найден · {_seconds(time.perf_counter() - started)}"
        )
        return session

    async def load_details(self, session: MeterSession) -> None:
        """Параллельно грузит все блоки прибора; каждый уходит в интерфейс по готовности."""
        async with asyncio.TaskGroup() as tg:
            tg.create_task(self._guarded(Section.INFO, lambda: self._load_info(session)))
            tg.create_task(self._guarded(Section.READINGS, lambda: self._load_readings(session)))
            tg.create_task(self._guarded(Section.LOAD, lambda: self._load_load(session)))
            tg.create_task(self._guarded(Section.EVENTS, lambda: self._load_events(session)))
        elapsed = _seconds(time.perf_counter() - session.started_at)
        self._status(f"Все данные получены · {elapsed}", StatusKind.OK)

    async def _load_info(self, session: MeterSession) -> dict[str, Any]:
        """Блок «Точка учёта»: договор и адрес."""
        info = build_point_info(await self._client.get_instance_info(session.identity.point_id))
        session.info = info
        return info.to_js()

    async def _fetch_readings(self, session: MeterSession) -> Readings:
        """Читает текущие показания из базы Пирамиды."""
        now = datetime.now().replace(microsecond=0)
        points = await self._client.read_meter_data(
            MeterDataReadRequest(
                instances_ids=[session.identity.point_id],
                parameters=list(CURRENT_PARAMETERS),
                start=now,
                finish=now,
                sources=[list(s) for s in CURRENT_SOURCES],
            )
        )
        readings = build_readings(points)
        session.readings = readings
        return readings

    async def _load_readings(self, session: MeterSession) -> dict[str, Any]:
        """Блок «Показания»."""
        readings = await self._fetch_readings(session)
        if readings.taken_at:
            self._status(f"Показания получены (на {fmt_dt(readings.taken_at)})")
        else:
            self._status("По прибору ещё нет ни одного опроса показаний", StatusKind.WARN)
        return readings.to_js()

    async def _fetch_load(self, session: MeterSession) -> LoadInfo:
        """Читает состояние реле и лимит."""
        points = await self._client.get_load_limit_states([session.identity.point_id])
        load = build_load_info(points)
        session.load = load
        return load

    async def _load_load(self, session: MeterSession) -> dict[str, Any]:
        """Блок «Нагрузка»."""
        load = await self._fetch_load(session)
        if load.relay:
            self._status(f"Реле: {load.relay.lower()} (на {fmt_dt(load.relay_at)})")
        return load.to_js()

    async def _fetch_events(self, session: MeterSession) -> list[MeterEvent]:
        """Читает журнал событий за всю историю (``events_history_years`` лет)."""
        end = datetime.now().replace(microsecond=0)
        start = _day_start(end.date() - timedelta(days=365 * self._settings.events_history_years))
        raw = await self._client.get_events(
            EventsRequest(
                ids=[session.identity.point_id], intervals=[Interval(begin=start, end=end)]
            )
        )
        events = to_meter_events(raw)
        session.events = events
        return events

    def _events_summary(self, events: list[MeterEvent]) -> dict[str, Any]:
        """Сводка по журналу для интерфейса: количество и тревожные события."""
        alarms = alarm_summary(events)
        if alarms:
            types = ", ".join(a.event_type.lower() for a in alarms)
            self._status(f"Внимание: в журнале есть тревожные события — {types}", StatusKind.WARN)
        return {
            "total": len(events),
            "importantTotal": sum(1 for e in events if e.important),
            "latestAt": events[0].to_js()["dt"] if events else None,
            "alarms": [a.to_js() for a in alarms],
        }

    async def _load_events(self, session: MeterSession) -> dict[str, Any]:
        """Блок «События» (для алярм-иконки и окна событий)."""
        return self._events_summary(await self._fetch_events(session))

    def events_page(
        self, session: MeterSession, *, offset: int, limit: int, important_only: bool
    ) -> EventsPage:
        """Порция событий для окна «События»."""
        return events_page(
            session.events or [], offset=offset, limit=limit, important_only=important_only
        )

    # ------------------------------------------------------------ обновление «с прибора»
    async def _refresh(
        self,
        section: Section,
        start_task: Callable[[], Awaitable[int]],
        reload: Callable[[], Awaitable[dict[str, Any]]],
        title: str,
    ) -> None:
        """Общий сценарий: задача опроса → ожидание → перечитать блок."""
        self._busy(section, busy=True)
        try:
            task_id = await start_task()
            self._status(f"{title}: задача №{task_id} создана")
            state = await self._wait(task_id, section)
            data = await reload()
        except asyncio.CancelledError:
            self._status(f"{title}: отменено", StatusKind.WARN)
            self._busy(section, busy=False)
            raise
        except PyramidError:
            self._busy(section, busy=False)
            raise
        self._part(section, data)
        self._busy(section, busy=False)
        if state.is_errors_detected:
            self._status(f"{title}: завершено с ошибками", StatusKind.WARN)
        else:
            self._status(f"{title}: данные обновлены", StatusKind.OK)

    async def refresh_readings(self, session: MeterSession) -> None:
        """Опросить прибор и обновить показания."""
        now = datetime.now().replace(microsecond=0)

        async def start() -> int:
            return await self._client.start_acquire(
                AcquireRequest(
                    instances_ids=[session.identity.point_id],
                    parameters=list(CURRENT_PARAMETERS),
                    start=_day_start(now.date()),
                    finish=now,
                )
            )

        await self._refresh(Section.READINGS, start, lambda: self._load_readings(session),
                            "Опрос показаний")  # fmt: skip

    async def refresh_load(self, session: MeterSession) -> None:
        """Опросить реле и лимит у прибора."""

        async def start() -> int:
            return await self._client.start_read_load_limit([session.identity.meter_id])

        await self._refresh(Section.LOAD, start, lambda: self._load_load(session),
                            "Опрос реле")  # fmt: skip

    async def refresh_events(self, session: MeterSession) -> None:
        """Вычитать журнал событий с прибора (с последнего известного события до сейчас)."""
        now = datetime.now().replace(microsecond=0)
        events = session.events or []
        since = events[0].dt if events else _day_start(now.date())

        async def start() -> int:
            return await self._client.start_read_events(
                StartReadEventsRequest(
                    event_sources_int_ref_names=[session.identity.point_id],
                    start_date=since,
                    end_date=now,
                )
            )

        await self._refresh(Section.EVENTS, start, lambda: self._load_events(session),
                            "Чтение журнала")  # fmt: skip

    # ------------------------------------------------------------ подневка
    async def _fetch_daily(
        self, session: MeterSession, start: date, end: date
    ) -> list[MeterPointData]:
        """Показания на начало суток за период."""
        return await self._client.read_meter_data(
            MeterDataReadRequest(
                instances_ids=[session.identity.point_id],
                parameters=list(DAILY_PARAMETERS),
                start=_day_start(start),
                finish=_day_start(end),
                sources=[list(s) for s in DAILY_SOURCES],
            ),
            no_limit=True,
        )

    async def daily_rows(self, session: MeterSession, start: date, end: date) -> list[DailyRow]:
        """Подневка для просмотра в программе (+1 день, чтобы посчитать расход за последний)."""
        points = await self._fetch_daily(session, start, end + timedelta(days=1))
        rows = build_daily_rows(points, start, end)
        filled = sum(1 for r in rows if r.t0 is not None)
        self._status(f"Подневка: {filled} из {len(rows)} дн. с показаниями")
        return rows

    async def export_daily(
        self, session: MeterSession, start: date, end: date, folder: Path
    ) -> Path:
        """Выгружает подневку в xlsx и возвращает путь к файлу."""
        points = await self._fetch_daily(session, start, end)
        caption = points[0].point_with_meter.meter.caption if points else session.identity.caption
        path = folder / _safe_filename(f"Показания на начало суток по {caption}.xlsx")
        await asyncio.to_thread(create_daily_workbook, points, path)
        return path

    # ------------------------------------------------------------ почасовка
    async def export_hourly(
        self, session: MeterSession, start: date, end: date, folder: Path
    ) -> Path:
        """Формирует почасовой отчёт в Пирамиде, ждёт и скачивает его."""
        identity = session.identity
        caption = (session.info.full_path if session.info else None) or identity.point_caption
        task = await self._client.create_hourly_report(
            _day_start(start), _day_start(end), [ReportNode(id=identity.point_id, caption=caption)]
        )
        await self._wait(task.task_id, Section.REPORT, log_type=REPORT_LOG_TYPE)
        content = await self._client.download_archive_report(task.archive_entry_id)
        timestamp = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
        name = _safe_filename(f"Почасовка {identity.model} №{identity.meter_num} {timestamp}.xlsx")
        path = folder / name
        await asyncio.to_thread(path.write_bytes, content)
        return path
