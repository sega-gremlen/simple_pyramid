"""Модели отчёта «02.01 Показания и профиль ЭЭ (30 и 60 мин) по точке учета (СРС)».

Payload отчёта — длинный список параметров в формате конструктора отчётов Пирамиды.
Формат повторяет то, что отправляет веб-интерфейс, байт-в-байт (проверяется тестом).
"""

import json
from datetime import datetime
from typing import Any

from pydantic import Field

from simple_pyramid.api.models.base import ApiModel, format_api_datetime
from simple_pyramid.api.models.meterdata import CLASSIFIER_ID

HOURLY_REPORT_ID = 12290958
HOURLY_REPORT_FORMAT_ID = -7128
HOURLY_REPORT_FILE_NAME = "02.01 Показания и профиль ЭЭ (30 и 60 мин) по точке учета (СРС).xlsx"


class ReportValue(ApiModel):
    """Значение параметра отчёта. Пустое значение сериализуется как ``{}``."""

    as_int: int | None = None
    as_float: float | None = None
    as_string: str | None = None
    as_boolean: bool | None = None
    as_date_time: str | None = None
    as_instance_link: dict[str, Any] | None = None
    as_class_link: dict[str, Any] | None = None

    @classmethod
    def full(cls, **values: Any) -> "ReportValue":
        """Значение со всеми полями (явные None), как шлёт веб-интерфейс."""
        base: dict[str, Any] = dict.fromkeys(cls.model_fields)
        base.update(values)
        return cls(**base)


class ReportParameter(ApiModel):
    """Параметр отчёта. Сериализуется с ``exclude_unset`` — состав ключей важен."""

    id: str
    parameter_name: str
    pointer_to_type: int | None
    data_type: int
    is_array: bool
    instances_tree_filter_detected: bool = False
    values: list[ReportValue]
    classifier_id: int | None
    discret: None = None
    constraint: str | None
    entities_links: list[Any] | None = None
    entities_links_ids: list[Any] = Field(default_factory=list)
    string_values: list[Any] | None = None
    constraint_value: dict[str, Any] | None


def _bool_param(param_id: str, name: str, *, value: bool) -> ReportParameter:
    """Параметр-флажок."""
    return ReportParameter(
        id=param_id,
        parameter_name=name,
        pointer_to_type=None,
        data_type=3,
        is_array=False,
        instances_tree_filter_detected=False,
        values=[ReportValue.full(as_boolean=value)],
        classifier_id=None,
        discret=None,
        constraint=None,
        entities_links_ids=[],
        constraint_value=None,
    )


def _empty_param(param_id: str, name: str, data_type: int) -> ReportParameter:
    """Параметр без значения (``values: [{}]``)."""
    return ReportParameter(
        id=param_id,
        parameter_name=name,
        pointer_to_type=None,
        data_type=data_type,
        is_array=False,
        instances_tree_filter_detected=False,
        values=[ReportValue()],
        classifier_id=None,
        discret=None,
        constraint=None,
        entities_links_ids=[],
        constraint_value=None,
    )


def _date_param(
    param_id: str, name: str, value: datetime, relative_discret: int
) -> ReportParameter:
    """Параметр-дата (начало/окончание периода)."""
    constraint = {
        "OffsetDiscret": {"TypeId": -1147, "Value": 0},
        "RelativeDiscret": relative_discret,
    }
    return ReportParameter(
        id=param_id,
        parameter_name=name,
        pointer_to_type=None,
        data_type=5,
        is_array=False,
        instances_tree_filter_detected=False,
        values=[ReportValue.full(as_date_time=format_api_datetime(value))],
        classifier_id=None,
        discret=None,
        constraint=json.dumps(constraint, ensure_ascii=False),
        entities_links_ids=[],
        constraint_value=constraint,
    )


def _class_link_param(
    *,
    param_id: str,
    name: str,
    pointer_to_type: int,
    data_type: int,
    caption: str,
    values: list[ReportValue],
    classifier_id: int | None,
) -> ReportParameter:
    """Параметр-ссылка на объекты классификатора (точки учёта, абоненты)."""
    constraint = {
        "Type": data_type,
        "Caption": caption,
        "Id": pointer_to_type,
        "PointerToType": None,
    }
    return ReportParameter(
        id=param_id,
        parameter_name=name,
        pointer_to_type=pointer_to_type,
        data_type=data_type,
        is_array=True,
        instances_tree_filter_detected=False,
        values=values,
        classifier_id=classifier_id,
        discret=None,
        constraint=json.dumps(constraint, ensure_ascii=False),
        entities_links=[],
        entities_links_ids=[],
        string_values=[],
        constraint_value=constraint,
    )


class ReportNode(ApiModel):
    """Точка учёта, по которой строится отчёт."""

    id: int
    caption: str


def build_hourly_report_payload(
    start: datetime, end: datetime, nodes: list[ReportNode]
) -> list[dict[str, Any]]:
    """Собирает payload для создания почасового отчёта (``createfilereportasync``)."""
    node_values = [ReportValue(as_instance_link=node.model_dump()) for node in nodes]
    params = [
        _class_link_param(
            param_id="ClassifierNodes", name="Точки учёта", pointer_to_type=-1478, data_type=9,
            caption="Объект классификатора", values=node_values, classifier_id=CLASSIFIER_ID,
        ),  # <-- подставлены переданные точки
        _class_link_param(
            param_id="ClassifierAbon", name="Абоненты", pointer_to_type=-1592, data_type=10,
            caption="Абоненты", values=[ReportValue()], classifier_id=None,
        ),
        _date_param("StartDt", "Начало периода", start, -5171),  # <-- дата начала
        _date_param("EndDt", "Окончание периода", end, -5169),  # <-- дата окончания
        _bool_param("bPokaz", "Выгружать показания", value=True),
        _bool_param("b30", "Выгружать 30 минут", value=True),
        _bool_param("b1h", "Выгружать 1 час", value=True),
        _bool_param("bNum", "Фильтр по номерам", value=False),
        _bool_param("bEquals", "Точное совпадение номера", value=False),
        _empty_param("sNum", "Номера ПУ", 4),
        _bool_param("bOcrugl", "Включить округление", value=False),
        _empty_param("iZnak", "Количество знаков (0-8)", 1),
    ]  # fmt: skip
    return [p.model_dump(mode="json", by_alias=True, exclude_unset=True) for p in params]


class ReportTask(ApiModel):
    """Ответ на создание отчёта."""

    task_id: int
    archive_entry_id: int | str


class ArchiveReportRequest(ApiModel):
    """Тело запроса ``POST /reports/getarchivereport/`` — скачать готовый файл."""

    user_id: int | str | None
    archive_entry_id: int | str
    keep_notification: bool = False
    file_name: str = HOURLY_REPORT_FILE_NAME
