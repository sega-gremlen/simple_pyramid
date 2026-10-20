"""FastAPI-приложение эмулятора: те же пути и форматы ответов, что у «Пирамиды»."""

import asyncio
import io
import json
import random
import secrets
import time
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Any

from fastapi import FastAPI, Header, HTTPException, Request, Response
from fastapi.responses import JSONResponse
from openpyxl import Workbook

from dev.mock_server.scenarios import MeterState, make_meter

PARAM_CAPTIONS: dict[int, tuple[str, str]] = {
    -2139: ("Энергия А- текущая", "Вт*ч"),
    4726239: ('Энергия А- текущая, Тарифная зона "День Двухзонный"', "Вт*ч"),
    4726797: ('Энергия А- текущая, Тарифная зона "Ночь Двухзонный"', "Вт*ч"),
    -1973: ("Энергия А+ текущая", "Вт*ч"),
    4726597: ('Энергия А+ текущая, Тарифная зона "День Двухзонный"', "Вт*ч"),
    4727155: ('Энергия А+ текущая, Тарифная зона "Ночь Двухзонный"', "Вт*ч"),
    -2143: ("Энергия Р- текущая", "ВАр*ч"),
    4726253: ('Энергия Р- текущая, Тарифная зона "День Двухзонный"', "ВАр*ч"),
    4726811: ('Энергия Р- текущая, Тарифная зона "Ночь Двухзонный"', "ВАр*ч"),
    -2141: ("Энергия Р+ текущая", "ВАр*ч"),
    4726243: ('Энергия Р+ текущая, Тарифная зона "День Двухзонный"', "ВАр*ч"),
    4726801: ('Энергия Р+ текущая, Тарифная зона "Ночь Двухзонный"', "ВАр*ч"),
    -2161: ("Энергия А+ на начало суток", "Вт*ч"),
    4726233: ('Энергия А+ на начало суток, Тарифная зона "День Двухзонный"', "Вт*ч"),
    4726791: ('Энергия А+ на начало суток, Тарифная зона "Ночь Двухзонный"', "Вт*ч"),
}
DAILY_IDS = {-2161, 4726233, 4726791}
DAILY_KWH_PER_DAY = (6_000, 3_000)  # средний расход днём/ночью, Вт·ч


def iso(value: datetime | None) -> str | None:
    """Дата в формате Пирамиды (миллисекунды, без таймзоны)."""
    return value.isoformat(timespec="milliseconds") if value else None


def parse_dt(value: str) -> datetime:
    """Разбор даты из запроса."""
    return datetime.fromisoformat(value)


@dataclass
class MockTask:
    """Фоновая задача эмулятора."""

    id: int
    descriptor: str
    duration: float
    log_template: list[str]
    fail: bool = False
    on_complete: Callable[[], None] | None = None
    started: float = field(default_factory=time.monotonic)
    completed: bool = False

    def state(self) -> dict[str, Any]:
        """Состояние задачи с логом, растущим по мере выполнения."""
        elapsed = time.monotonic() - self.started
        done = elapsed >= self.duration
        if done and not self.completed:
            self.completed = True
            if self.on_complete and not self.fail:
                self.on_complete()
        share = 1.0 if done else elapsed / self.duration
        visible = self.log_template[: max(1, int(len(self.log_template) * share))]
        now = datetime.now()
        log = [{"message": msg, "logMessageType": 0, "level": 1, "dt": iso(now)} for msg in visible]
        # Немного «сырых» Tx/Rx — UI должен их отфильтровать (level=0)
        log.insert(1, {"message": "[Мегафон] Tx: 7E_A0_08_02_23_61_53_D7_E4_7E_",
                       "logMessageType": 0, "level": 0, "dt": iso(now)})  # fmt: skip
        if done and self.fail:
            log.append({"message": "Ошибка выполнения запроса. Устройство не отвечает",
                        "logMessageType": 1, "level": 1, "dt": iso(now)})  # fmt: skip
        return {
            "isCompleted": done,
            "extendedCompletionStatus": 0,
            "isErrorsDetected": done and self.fail,
            "information": "",
            "informationFormat": 1,
            "customData": {"dataCount": len(log) if done else 0},
            "taskDuration": f"00:00:{min(elapsed, 59):09.6f}",
            "log": log,
            "progress": 0,
        }


@dataclass
class MockState:
    """Всё состояние эмулятора."""

    meters: dict[str, MeterState] = field(default_factory=dict)
    by_point: dict[int, MeterState] = field(default_factory=dict)
    by_meter: dict[int, MeterState] = field(default_factory=dict)
    tasks: dict[int, MockTask] = field(default_factory=dict)
    tokens: dict[str, float] = field(default_factory=dict)
    reports: dict[str, tuple[str, str]] = field(default_factory=dict)
    next_task: int = 704_000

    def meter(self, number: str, index: int = 0) -> MeterState:
        """Прибор по номеру (создаётся при первом обращении)."""
        key = f"{number}#{index}"
        if key not in self.meters:
            meter = make_meter(number, index)
            self.meters[key] = meter
            self.by_point[meter.point_id] = meter
            self.by_meter[meter.meter_id] = meter
        return self.meters[key]

    def point(self, point_id: int) -> MeterState:
        """Прибор по id точки учёта."""
        if point_id not in self.by_point:
            raise HTTPException(404, "Точка учёта не найдена")
        return self.by_point[point_id]

    def add_task(self, task: MockTask) -> int:
        """Регистрирует задачу."""
        self.tasks[task.id] = task
        return task.id

    def new_task_id(self, *, negative: bool = False) -> int:
        """Очередной id задачи (у задач нагрузки в Пирамиде id отрицательные)."""
        self.next_task += 1
        return -(self.next_task % 10_000) if negative else self.next_task


def create_app(
    *,
    latency: tuple[float, float] = (0.2, 1.5),
    task_duration: tuple[float, float] = (5.0, 12.0),
    token_ttl: float = 30 * 60,
) -> FastAPI:
    """Создаёт приложение эмулятора.

    Args:
        latency: случайная задержка ответа, сек (min, max). ``(0, 0)`` — без задержек.
        task_duration: длительность фоновых задач, сек (min, max).
        token_ttl: время жизни токена, сек (после — 401, клиент должен перелогиниться).
    """
    app = FastAPI(title="Эмулятор Пирамиды")
    state = MockState()
    app.state.mock = state
    rnd = random.Random()

    def duration(meter: MeterState | None = None) -> float:
        if meter and meter.behavior.slow_failing_tasks:
            return 40.0
        lo, hi = task_duration
        return rnd.uniform(lo, hi) if hi > 0 else 0.0

    @app.middleware("http")
    async def delay_and_auth(
        request: Request, call_next: Callable[[Request], Awaitable[Response]]
    ) -> Response:
        lo, hi = latency
        if hi > 0:
            await asyncio.sleep(rnd.uniform(lo, hi))
        path = request.url.path
        if path.startswith("/api/v1/") and not path.endswith("/auth/login/"):
            auth = request.headers.get("Authorization", "")
            token = auth.removeprefix("Bearer ")
            expires = state.tokens.get(token)
            if not expires or expires < time.monotonic():
                return JSONResponse({"message": "Unauthorized"}, status_code=401)
        return await call_next(request)

    # ------------------------------------------------------------------ auth
    @app.post("/api/v1/auth/login/")
    async def login(body: dict[str, Any]) -> dict[str, Any]:
        if body.get("password") == "wrong" or not body.get("username"):
            raise HTTPException(400, "Неверный логин или пароль")
        token = secrets.token_urlsafe(24)
        state.tokens[token] = time.monotonic() + token_ttl
        return {"userId": 688, "tokens": {"accessToken": token, "refreshToken": None}}

    # ------------------------------------------------------------------ instances
    @app.post("/api/v1/rdinstance/getinstances/")
    async def get_instances(body: dict[str, Any]) -> dict[str, Any]:
        # filter = '["-1494", "contains", "<номер>"]'
        number = str(json.loads(body["options"]["filter"])[2]).strip()
        meters: list[MeterState] = []
        probe = state.meter(number)
        if not probe.behavior.not_found:
            meters = [probe]
            if probe.behavior.multiple:
                meters.append(state.meter(number, index=1))
        data = [
            {
                "caption": m.caption,
                "id": m.meter_id,
                "-1494": m.number,
                "-56855": m.model,
                "-8295": {"id": m.point_id, "caption": m.point_caption},
                "-3134": [
                    {"id": m.point_id + 100 + i, "caption": r} for i, r in enumerate(m.routes)
                ],
                "-1498": "2021-01-01T00:00:00",
            }
            for m in meters
        ]
        return {"data": data, "totalCount": len(data)}

    @app.get("/api/v1/rdinstance/getinstanceinfo/")
    async def get_instance_info(instanceId: int) -> dict[str, Any]:  # noqa: N803
        m = state.point(instanceId)
        return {
            "instance": {
                "id": m.point_id,
                "-10024": [{"id": m.point_id - 1, "caption": m.account}],
                "-13379": m.full_path,
            }
        }

    # ------------------------------------------------------------------ meterdata
    def current_values(m: MeterState, pid: int) -> tuple[float | None, datetime | None]:
        if m.readings_dt is None:
            return None, None
        a_plus = m.a_plus_t1 + m.a_plus_t2
        a_minus = m.a_minus_t1 + m.a_minus_t2
        values = {
            -1973: a_plus, 4726597: m.a_plus_t1, 4727155: m.a_plus_t2,
            -2139: a_minus, 4726239: m.a_minus_t1, 4726797: m.a_minus_t2,
            -2141: a_plus * 0.02, 4726243: m.a_plus_t1 * 0.02, 4726801: m.a_plus_t2 * 0.02,
            -2143: a_plus * 0.3, 4726253: m.a_plus_t1 * 0.3, 4726811: m.a_plus_t2 * 0.3,
        }  # fmt: skip
        return round(values.get(pid, 0.0)), m.readings_dt

    def daily_values(
        m: MeterState, pid: int, start: datetime, finish: datetime
    ) -> list[dict[str, Any]]:
        result = []
        day = start.replace(hour=0, minute=0, second=0, microsecond=0)
        today = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)
        while day <= min(finish, today):
            days_back = (today - day).days
            if m.readings_dt is not None and days_back % 17 != 5:  # иногда дня нет
                t1 = m.a_plus_t1 - DAILY_KWH_PER_DAY[0] * days_back
                t2 = m.a_plus_t2 - DAILY_KWH_PER_DAY[1] * days_back
                value = {-2161: t1 + t2, 4726233: t1, 4726791: t2}[pid]
                result.append({
                    "registerDt": iso(day + timedelta(hours=6, minutes=50)),
                    "sourceKind": -3718,
                    "sourceInfo": m.caption,
                    "statuses": [],
                    "value": max(0.0, float(round(value))),
                    "valueDt": iso(day),
                })  # fmt: skip
            day += timedelta(days=1)
        return result

    @app.post("/api/v1/meterdata/read/")
    async def meterdata_read(body: dict[str, Any]) -> list[dict[str, Any]]:
        result = []
        for pid_point in body["instancesIds"]:
            m = state.point(int(pid_point))
            params = []
            for pid in body["parameters"]:
                caption, unit = PARAM_CAPTIONS.get(pid, (f"Параметр {pid}", "Вт*ч"))
                if pid in DAILY_IDS:
                    values = daily_values(m, pid, parse_dt(body["start"]), parse_dt(body["finish"]))
                else:
                    value, dt = current_values(m, pid)
                    values = [{
                        "registerDt": iso(dt),
                        "sourceKind": -3718,
                        "sourceInfo": m.caption,
                        "statuses": [],
                        "value": float(value) if value is not None else None,
                        "valueDt": None,
                    }] if dt else []  # fmt: skip
                params.append({
                    "parameter": {"id": pid, "caption": caption, "unit": unit, "readonly": False},
                    "hasApprovedData": False,
                    "values": values,
                })  # fmt: skip
            result.append({
                "pointWithMeter": {
                    "isMeterPointDisabled": None,
                    "meter": {"id": m.meter_id, "caption": m.caption},
                    "id": m.point_id,
                    "caption": m.point_caption,
                },
                "parametersData": params,
                "lossesInfo": [],
            })  # fmt: skip
        return result

    @app.post("/api/v1/meterdata/acquire/")
    async def meterdata_acquire(body: dict[str, Any]) -> int:
        m = state.point(int(body["instancesIds"][0]))
        caption = m.caption
        log = [
            "Начало выполнения задания",
            "Производится проверка наличия данных в БД...",
            f"Выполняется запрос данных по параметру Энергия А+ текущая ({caption})",
            f"Ожидание ресурсов для {caption}",
            f"{caption}, устанавливается соединение {m.routes[0]}",
            f"Установлено соединение {m.routes[0]}",
            f"Сбор данных с {caption} на установленном соединении",
            f"{caption} - Энергия А+ текущая - получено значение",
            "Ожидание завершения записи данных в БД",
            "Данные записаны",
            "Окончание выполнения задания",
        ]
        return state.add_task(MockTask(
            id=state.new_task_id(), descriptor="Сбор данных", duration=duration(m),
            log_template=log, fail=m.behavior.slow_failing_tasks,
            on_complete=lambda: m.poll_readings(datetime.now()),
        ))  # fmt: skip

    # ------------------------------------------------------------------ load / limit
    def load_point(m: MeterState) -> dict[str, Any]:
        read_op = (
            {"type": -15838, "owner": "Тестовый пользователь", "dt": iso(m.load_read_dt),
             "executeStatus": 0}
            if m.load_read_dt else None
        )  # fmt: skip
        value_dt = None if m.load_read_dt else iso(m.load_dt)
        caption = "Включено" if m.relay_on else "Отключено"
        return {
            "loadState": {
                "isWaiting": False,
                "value": {"id": -85404 if m.relay_on else -85406, "caption": caption},
                "valueDt": value_dt,
                "lastSuccessReadOperation": read_op,
                "executingOperation": None,
                "errorOperation": None,
            },
            "limitState": {
                "value": m.limit,
                "valueDt": value_dt,
                "syncValueDt": value_dt,
                "lastSuccessReadOperation": read_op,
            },
            "maxPowerConsumption": None,
            "meter": {"id": m.meter_id, "caption": m.caption},
            "id": m.point_id,
            "caption": m.point_caption,
        }

    @app.post("/api/v1/loadlimitmanagement/getmeterpointswithloadandlimitstate/")
    async def load_states(body: dict[str, Any]) -> list[dict[str, Any]]:
        return [load_point(state.point(int(pid))) for pid in body["instancesIds"]]

    @app.post("/api/v1/loadlimitmanagement/startasynctaskreadloadlimitstates/")
    async def load_start_read(body: dict[str, Any]) -> int:
        meter_id = int(body["metersId"][0])
        if meter_id not in state.by_meter:
            raise HTTPException(404, "Прибор не найден")
        m = state.by_meter[meter_id]

        def complete() -> None:
            m.load_read_dt = datetime.now()

        log = [
            "Начало выполнения задания",
            f"Выполняется запрос состояния Состояние нагрузки ({m.caption})",
            f"Выполняется запрос состояния Ограничение нагрузки ({m.caption})",
            f"{m.caption}, устанавливается соединение {m.routes[0]}",
            f"Установлено соединение {m.routes[0]}",
            "Режим реле управления нагрузкой: 0. Блокировка РУН отключена (режим выкл).",
            f"По заданию получено значение Состояние нагрузки {'Включено' if m.relay_on else 'Отключено'}",
            f"По заданию получено значение Ограничение нагрузки {int(m.limit)}",
            "Окончание выполнения задания",
        ]
        return state.add_task(MockTask(
            id=state.new_task_id(negative=True),
            descriptor="Чтение состояния нагрузки и лимита мощности",
            duration=duration(m), log_template=log, fail=m.behavior.slow_failing_tasks,
            on_complete=complete,
        ))  # fmt: skip

    # ------------------------------------------------------------------ events
    @app.post("/api/v1/events/geteventsforobjects/")
    async def get_events(body: dict[str, Any]) -> list[dict[str, Any]]:
        m = state.point(int(body["ids"][0]))
        interval = body["intervals"][0]
        begin, end = parse_dt(interval["begin"]), parse_dt(interval["end"])
        events = [e for e in m.events if begin <= e["dt"] <= end]  # type: ignore[operator]
        events.sort(key=lambda e: e["dt"], reverse=True)  # type: ignore[arg-type, return-value]
        return [
            {
                "compoundKey": f"{e['dt']:%d.%m.%Y %H:%M:%S}_-10640_-18172",
                "callerId": -10640,
                "categoryId": -18172,
                "sideEvent": "События сервера",
                "caller": "Сервис сбора данных",
                **e,
                "dt": iso(e["dt"]),  # type: ignore[arg-type]
            }
            for e in events
        ]

    @app.post("/api/v1/events/startreadeventsasync/")
    async def events_start_read(body: dict[str, Any]) -> int:
        m = state.point(int(body["eventSourcesIntRefNames"][0]))

        def complete() -> None:
            m.events.append({
                "dt": datetime.now() - timedelta(minutes=1),
                "eventType": "Выполнен анализ времени устройства",
                "description": "Расхождение времени - 2 сек.",
                "categoryCaption": "События подсистемы сбора",
                "eventSender": m.caption,
            })  # fmt: skip

        log = ["Начало выполнения задания", f"Чтение журнала событий {m.caption}",
               "Окончание выполнения задания"]  # fmt: skip
        return state.add_task(MockTask(
            id=state.new_task_id(), descriptor="Сбор журнала событий", duration=duration(m),
            log_template=log, fail=m.behavior.slow_failing_tasks, on_complete=complete,
        ))  # fmt: skip

    # ------------------------------------------------------------------ tasks
    def task(task_id: int) -> MockTask:
        if task_id not in state.tasks:
            raise HTTPException(404, "Задача не найдена")
        return state.tasks[task_id]

    @app.get("/api/v1/backgroundtasks/getbackgroundtask/")
    async def get_background_task(backgroundTaskId: int) -> dict[str, Any]:  # noqa: N803
        t = task(backgroundTaskId)
        st = t.state()
        st["log"] = None  # первый ответ — без лога, как в Пирамиде
        return {
            "taskState": st,
            "shortTaskDescriptor": t.descriptor,
            "canBeInBackground": True,
            "logType": 2,
            "isLogIncrement": False,
            "id": t.id,
        }

    @app.get("/api/v1/backgroundtasks/getbackgroundtaskstate/")
    async def get_background_task_state(
        backgroundTaskId: int,  # noqa: N803
        logType: int = 2,  # noqa: N803
    ) -> dict[str, Any]:
        return task(backgroundTaskId).state()

    # ------------------------------------------------------------------ reports
    @app.post("/api/v1/reports/createfilereportasync/")
    async def create_report(body: list[dict[str, Any]]) -> dict[str, Any]:
        params = {p["id"]: p for p in body}
        node = params["ClassifierNodes"]["values"][0]["asInstanceLink"]
        start = params["StartDt"]["values"][0]["asDateTime"]
        end = params["EndDt"]["values"][0]["asDateTime"]
        entry = secrets.token_hex(6)
        state.reports[entry] = (node["caption"], f"{start} — {end}")
        task_id = state.add_task(MockTask(
            id=state.new_task_id(), descriptor="Формирование отчёта", duration=duration() / 2,
            log_template=["Начало формирования отчёта", "Отчёт сформирован"],
        ))  # fmt: skip
        return {"taskId": task_id, "archiveEntryId": entry}

    @app.post("/api/v1/reports/getarchivereport/")
    async def archive_report(body: dict[str, Any]) -> Response:
        caption, period = state.reports.get(body["archiveEntryId"], ("?", "?"))
        wb = Workbook()
        ws = wb.active
        assert ws is not None  # noqa: S101
        ws.append(["Эмулятор Пирамиды — почасовой отчёт"])
        ws.append(["Точка учёта", caption])
        ws.append(["Период", period])
        ws.append(["Время", "A+, кВт*ч"])
        for hour in range(24):
            ws.append([f"{hour:02d}:00", round(rnd.uniform(0.1, 2.5), 3)])
        buf = io.BytesIO()
        wb.save(buf)
        media = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
        return Response(buf.getvalue(), media_type=media)

    @app.get("/health")
    async def health(x_probe: str | None = Header(default=None)) -> dict[str, Any]:
        return {"ok": True, "meters": len(state.meters), "tasks": len(state.tasks)}

    return app
