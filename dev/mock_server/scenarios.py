"""Сценарии эмулятора: какое поведение у какого номера ПУ.

Номер ищется по вхождению (как в Пирамиде, фильтр ``contains``). Префиксы:

* ``000…`` — прибор не найден;
* ``111…`` — найдено несколько приборов;
* ``222…`` — по прибору ещё нет ни одного опроса (показания пустые);
* ``333…`` — три маршрута связи;
* ``555…`` — реле отключено;
* ``777…`` — в журнале есть тревожные события (вскрытие, сброс пломб);
* ``999…`` — опрос прибора идёт долго (~40 с) и завершается с ошибкой — для проверки отмены;
* любой другой номер — обычный прибор с одним маршрутом.

Логин — любой, пароль ``wrong`` — «неверный пароль».
"""

import hashlib
import random
from dataclasses import dataclass, field
from datetime import datetime, timedelta

MODELS = (
    "Нартис-И100 (СПОДЭС)Split",
    "РиМ 489.26 (СПОДЭС)",
    "Милур 107S (СПОДЭС)",
    "Меркурий 234 ARTM2-00 (СПОДЭС)",
)
STREETS = ("ул Лесная", "ул Солнечная", "ул Центральная", "ул Садовая", "пер Школьный")
VILLAGES = ("село Демидовка", "село Рамено", "поселок Новая Крымза", "село Заборовка")
OPERATORS = ("Мегафон", "МТС", "Билайн")


@dataclass
class Behavior:
    """Особенности сценария."""

    not_found: bool = False
    multiple: bool = False
    no_readings: bool = False
    routes: int = 1
    relay_off: bool = False
    alarms: bool = False
    slow_failing_tasks: bool = False


def behavior_for(number: str) -> Behavior:
    """Поведение по номеру ПУ."""
    # Ведущие нули не важны (кроме «000» — это отдельный сценарий «не найден»)
    core = number.lstrip("0")
    return Behavior(
        not_found=number.startswith("000") or not core,
        multiple=core.startswith("111"),
        no_readings=core.startswith("222"),
        routes=3 if core.startswith("333") else 1,
        relay_off=core.startswith("555"),
        alarms=core.startswith("777"),
        slow_failing_tasks=core.startswith("999"),
    )


def _seed(number: str) -> int:
    """Стабильное зерно случайностей по номеру."""
    return int(hashlib.sha256(number.encode()).hexdigest()[:8], 16)


@dataclass
class MeterState:
    """Состояние эмулируемого прибора (меняется после опросов)."""

    number: str
    behavior: Behavior
    meter_id: int
    point_id: int
    model: str
    address: str
    routes: list[str]
    account: str
    # Показания, Вт·ч: (A+ день, A+ ночь, A- день, A- ночь, R+, R-)
    a_plus_t1: float
    a_plus_t2: float
    a_minus_t1: float
    a_minus_t2: float
    readings_dt: datetime | None
    relay_on: bool
    limit: float
    load_dt: datetime
    load_read_dt: datetime | None = None
    events: list[dict[str, object]] = field(default_factory=list)

    @property
    def caption(self) -> str:
        """Подпись прибора, как в Пирамиде."""
        return f"{self.model}, №{self.number}"

    @property
    def point_caption(self) -> str:
        """Полный путь точки учёта (иерархия с обратными слэшами)."""
        return (
            "Самарская обл\\Жигулевское ПО/Сызранский РЭС/Сызранский р-н\\"
            + self.address.replace(", ", "\\")
            + f"\\{self.caption}"
        )

    @property
    def full_path(self) -> str:
        """Атрибут -13379 — путь через запятые."""
        return "Самарская обл, Жигулевское ПО/Сызранский РЭС/Сызранский р-н, " + self.address

    def poll_readings(self, now: datetime) -> None:
        """Опрос прибора «сейчас»: показания немного подрастают."""
        rnd = random.Random(now.timestamp())
        self.a_plus_t1 += rnd.randint(50, 900)
        self.a_plus_t2 += rnd.randint(20, 400)
        self.readings_dt = now


def _morning(days_ago: int = 0) -> datetime:
    """Время ежедневного утреннего опроса.

    Ночью, до 06:45, сегодняшнего опроса ещё не было — последний был вчера. Иначе дата опроса
    оказывалась в будущем, и ручной опрос выглядел «старее» утреннего (тесты падали ночью).
    """
    now = datetime.now()
    today = now.replace(hour=6, minute=45, second=31, microsecond=352000)
    if today > now:
        today -= timedelta(days=1)
    return today - timedelta(days=days_ago)


def _time_sync_events(caption: str, days: int) -> list[dict[str, object]]:
    """Ежедневные события коррекции времени (самые частые в реальном журнале)."""
    result: list[dict[str, object]] = []
    for d in range(days):
        base = _morning(d).replace(minute=44)
        result += [
            {
                "dt": base,
                "eventType": "Команда коррекции времени передана в прибор",
                "description": "Передаваемое значение дельты, сек -4",
                "categoryCaption": "События коррекции времени устройства",
            },
            {
                "dt": base + timedelta(seconds=1),
                "eventType": "Коррекция времени выполнена успешно",
                "description": "",
                "categoryCaption": "События коррекции времени устройства",
            },
            {
                "dt": base + timedelta(seconds=3),
                "eventType": "Выполнен анализ времени устройства",
                "description": f"Расхождение после синхронизации - {58 + d % 2} мин. {d % 60} сек.",
                "categoryCaption": "События подсистемы сбора",
            },
        ]
    for e in result:
        e["eventSender"] = caption
    return result


def _special_events(behavior: Behavior, caption: str) -> list[dict[str, object]]:
    """Важные и тревожные события сценария."""
    specials: list[tuple[int, str, str]] = [
        (12, "Отключение нагрузки", "Отключение по команде оператора"),
        (11, "Включение нагрузки", ""),
        (11, "Разрешение включения нагрузки", ""),
    ]
    if behavior.alarms:
        specials += [
            (3, "Вскрытие элемента устройства", "Вскрытие клеммной крышки"),
            (3, "Закрытие элемента устройства", "Закрытие клеммной крышки"),
            (20, "Выполнен сброс состояний пломб", ""),
            (40, "Попытка несанкционированного доступа", "Неверный пароль, уровень доступа 2"),
        ]
    return [
        {
            "dt": _morning(days) - timedelta(hours=3, minutes=days),
            "eventType": event_type,
            "description": description,
            "categoryCaption": "События прибора учёта",
            "eventSender": caption,
        }
        for days, event_type, description in specials
    ]


def make_meter(number: str, index: int = 0) -> MeterState:
    """Создаёт детерминированный прибор по номеру."""
    behavior = behavior_for(number)
    rnd = random.Random(_seed(number) + index)
    point_id = 21_000_000 + rnd.randint(0, 999_999)
    model = rnd.choice(MODELS)
    address = f"{rnd.choice(VILLAGES)}, {rnd.choice(STREETS)}, д {rnd.randint(1, 150)}"
    routes = []
    for i in range(behavior.routes):
        operator = rnd.choice(OPERATORS)
        phone = f"+7927{rnd.randint(1_000_000, 9_999_999)}"
        ip = f"10.{rnd.randint(1, 250)}.{rnd.randint(1, 250)}.{rnd.randint(2, 250)}"
        routes.append(f"{operator}, {phone}, {ip}, порт {5000 + i * 59}")
    meter = MeterState(
        number=number,
        behavior=behavior,
        meter_id=point_id - 2,
        point_id=point_id,
        model=model,
        address=address,
        routes=routes,
        account=f"Н. Н. Н. №0133{rnd.randint(10_000_000, 99_999_999)}",
        a_plus_t1=float(rnd.randint(1_000_000, 12_000_000)),
        a_plus_t2=float(rnd.randint(500_000, 6_000_000)),
        a_minus_t1=float(rnd.choice([0, 0, 120])),
        a_minus_t2=0.0,
        readings_dt=None if behavior.no_readings else _morning() - timedelta(minutes=14),
        relay_on=not behavior.relay_off,
        limit=15000.0,
        load_dt=_morning(),
    )
    caption = meter.caption
    meter.events = _time_sync_events(caption, 60) + _special_events(behavior, caption)
    return meter
