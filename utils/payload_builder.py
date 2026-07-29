from datetime import datetime
import json
from pathlib import Path


def _build_login_url() -> str:
    """Добавляет параметр timeZoneOffset к URL логина."""
    
    return f"{self.login_url}?timeZoneOffset={self.timezone_offset}"


def _build_task_create_file_report_async(start_str: str,
                                         end_str: str,
                                         nodes_values: list,
                                         ) -> list:
    """Собирает payload для task_create_file_report_async"""
    
    payload = [
            {
                "id": "ClassifierNodes",
                "parameterName": "Точки учёта",
                "pointerToType": -1478,
                "dataType": 9,
                "isArray": True,
                "instancesTreeFilterDetected": False,
                "values": nodes_values,                # <-- подставлены переданные точки
                "classifierId": 2481,
                "discret": None,
                "constraint": json.dumps({
                    "Type": 9,
                    "Caption": "Объект классификатора",
                    "Id": -1478,
                    "PointerToType": None
                }, ensure_ascii=False),
                "entitiesLinks": [],
                "entitiesLinksIds": [],
                "stringValues": [],
                "constraintValue": {
                    "Type": 9,
                    "Caption": "Объект классификатора",
                    "Id": -1478,
                    "PointerToType": None
                }
            },
            {
                "id": "ClassifierAbon",
                "parameterName": "Абоненты",
                "pointerToType": -1592,
                "dataType": 10,
                "isArray": True,
                "instancesTreeFilterDetected": False,
                "values": [{}],
                "classifierId": None,
                "discret": None,
                "constraint": json.dumps({
                    "Type": 10,
                    "Caption": "Абоненты",
                    "Id": -1592,
                    "PointerToType": None
                }, ensure_ascii=False),
                "entitiesLinks": [],
                "entitiesLinksIds": [],
                "stringValues": [],
                "constraintValue": {
                    "Type": 10,
                    "Caption": "Абоненты",
                    "Id": -1592,
                    "PointerToType": None
                }
            },
            {
                "id": "StartDt",
                "parameterName": "Начало периода",
                "pointerToType": None,
                "dataType": 5,
                "isArray": False,
                "instancesTreeFilterDetected": False,
                "values": [
                    {
                        "asInt": None, "asFloat": None, "asString": None,
                        "asBoolean": None,
                        "asDateTime": start_str,         # <-- подставлена дата начала
                        "asInstanceLink": None, "asClassLink": None
                    }
                ],
                "classifierId": None,
                "discret": None,
                "constraint": json.dumps({
                    "OffsetDiscret": {"TypeId": -1147, "Value": 0},
                    "RelativeDiscret": -5171
                }, ensure_ascii=False),
                "entitiesLinksIds": [],
                "constraintValue": {
                    "OffsetDiscret": {"TypeId": -1147, "Value": 0},
                    "RelativeDiscret": -5171
                }
            },
            {
                "id": "EndDt",
                "parameterName": "Окончание периода",
                "pointerToType": None,
                "dataType": 5,
                "isArray": False,
                "instancesTreeFilterDetected": False,
                "values": [
                    {
                        "asInt": None, "asFloat": None, "asString": None,
                        "asBoolean": None,
                        "asDateTime": end_str,           # <-- подставлена дата окончания
                        "asInstanceLink": None, "asClassLink": None
                    }
                ],
                "classifierId": None,
                "discret": None,
                "constraint": json.dumps({
                    "OffsetDiscret": {"TypeId": -1147, "Value": 0},
                    "RelativeDiscret": -5169
                }, ensure_ascii=False),
                "entitiesLinksIds": [],
                "constraintValue": {
                    "OffsetDiscret": {"TypeId": -1147, "Value": 0},
                    "RelativeDiscret": -5169
                }
            },
            {
                "id": "bPokaz",
                "parameterName": "Выгружать показания",
                "pointerToType": None,
                "dataType": 3,
                "isArray": False,
                "instancesTreeFilterDetected": False,
                "values": [{"asInt": None, "asFloat": None, "asString": None,
                            "asBoolean": True, "asDateTime": None,
                            "asInstanceLink": None, "asClassLink": None}],
                "classifierId": None, "discret": None, "constraint": None,
                "entitiesLinksIds": [], "constraintValue": None
            },
            {
                "id": "b30",
                "parameterName": "Выгружать 30 минут",
                "pointerToType": None,
                "dataType": 3,
                "isArray": False,
                "instancesTreeFilterDetected": False,
                "values": [{"asInt": None, "asFloat": None, "asString": None,
                            "asBoolean": True, "asDateTime": None,
                            "asInstanceLink": None, "asClassLink": None}],
                "classifierId": None, "discret": None, "constraint": None,
                "entitiesLinksIds": [], "constraintValue": None
            },
            {
                "id": "b1h",
                "parameterName": "Выгружать 1 час",
                "pointerToType": None,
                "dataType": 3,
                "isArray": False,
                "instancesTreeFilterDetected": False,
                "values": [{"asInt": None, "asFloat": None, "asString": None,
                            "asBoolean": True, "asDateTime": None,
                            "asInstanceLink": None, "asClassLink": None}],
                "classifierId": None, "discret": None, "constraint": None,
                "entitiesLinksIds": [], "constraintValue": None
            },
            {
                "id": "bNum",
                "parameterName": "Фильтр по номерам",
                "pointerToType": None,
                "dataType": 3,
                "isArray": False,
                "instancesTreeFilterDetected": False,
                "values": [{"asInt": None, "asFloat": None, "asString": None,
                            "asBoolean": False, "asDateTime": None,
                            "asInstanceLink": None, "asClassLink": None}],
                "classifierId": None, "discret": None, "constraint": None,
                "entitiesLinksIds": [], "constraintValue": None
            },
            {
                "id": "bEquals",
                "parameterName": "Точное совпадение номера",
                "pointerToType": None,
                "dataType": 3,
                "isArray": False,
                "instancesTreeFilterDetected": False,
                "values": [{"asInt": None, "asFloat": None, "asString": None,
                            "asBoolean": False, "asDateTime": None,
                            "asInstanceLink": None, "asClassLink": None}],
                "classifierId": None, "discret": None, "constraint": None,
                "entitiesLinksIds": [], "constraintValue": None
            },
            {
                "id": "sNum",
                "parameterName": "Номера ПУ",
                "pointerToType": None,
                "dataType": 4,
                "isArray": False,
                "instancesTreeFilterDetected": False,
                "values": [{}],
                "classifierId": None, "discret": None, "constraint": None,
                "entitiesLinksIds": [], "constraintValue": None
            },
            {
                "id": "bOcrugl",
                "parameterName": "Включить округление",
                "pointerToType": None,
                "dataType": 3,
                "isArray": False,
                "instancesTreeFilterDetected": False,
                "values": [{"asInt": None, "asFloat": None, "asString": None,
                            "asBoolean": False, "asDateTime": None,
                            "asInstanceLink": None, "asClassLink": None}],
                "classifierId": None, "discret": None, "constraint": None,
                "entitiesLinksIds": [], "constraintValue": None
            },
            {
                "id": "iZnak",
                "parameterName": "Количество знаков (0-8)",
                "pointerToType": None,
                "dataType": 1,
                "isArray": False,
                "instancesTreeFilterDetected": False,
                "values": [{}],
                "classifierId": None, "discret": None, "constraint": None,
                "entitiesLinksIds": [], "constraintValue": None
            }
        ]
    
    return payload