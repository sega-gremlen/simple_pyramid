from typing import Optional, Dict, Any
import re
import urllib3
from datetime import datetime, timedelta
import os
from pathlib import Path
import json
from dataclasses import dataclass
import time


import requests


from config import settings
from utils.xlsx_exporter import create_excel_from_json
from utils import payload_builder


urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)


@dataclass
class Meter:
    """Объект счетчик. Собирает в себе все нужные данные"""
    
    # Номер счетчика
    meter_num: str
    # ID счетчика
    instance_id: str
    # Тип счетчика
    model: str
    # Маршруты
    routes: list
    # Иерархиеческий путь
    full_path: str
    # Адрес (последний элемент в иерархии)
    address: str
    # ЛС
    contract_num: str
    
    # Показания (дата)
    meter_data_datetime: datetime
    
    # Показания по тарифам (A+)
    t0plus: float
    t1plus: float
    t2plus: float
    
    # Показания по тарифам (A-)
    t0minus: float
    t1minus: float
    t2minus: float
    
    
class PyramidApiClient:
    """
    Клиент для работы с API пирамиды с Bearer-авторизацией.
    Автоматически получает токен при первом входе и подставляет его во все запросы.
    """

    def __init__(
        self,
        base_url: str = settings.PYRAMID_ROOT_API_URL,
        
        #endpoints
        login_endpoint: str = "/auth/login/",
        get_instances_endpoint: str = "/rdinstance/getinstances/",
        get_instance_info_endpoint: str = "/rdinstance/getinstanceinfo/",
        meterdata_read_endpoint: str = "/meterdata/read/",
        power_endpoint: str = "/loadlimitmanagement/startasynctaskwriteloadstate/",
        hours_report_endpoint: str = "/reports/createfilereportasync/?reportId=12290958&reportFormatDataId=-7128",
        getarchivereport_endpoinf: str = "/reports/getarchivereport/",
        getbackgroundtaskstate_endpoint: str = "/backgroundtasks/getbackgroundtaskstate/",
        
    ) -> None:
        """
        Инициализация клиента.

        :param base_url: Базовый URL API (без завершающего слеша)
        :param login_endpoint: Путь к эндпоинту логина (относительно base_url)
        :param timezone_offset: Смещение часового пояса в минутах (по умолчанию -240)
        """
        self.base_url: str = base_url.rstrip('/')
        self.login_url: str = f"{self.base_url}{login_endpoint}?timeZoneOffset=-240"
        self.get_instances_url: str = f"{self.base_url}{get_instances_endpoint}"
        self.get_instance_info_url: str = f"{self.base_url}{get_instance_info_endpoint}"
        self.meterdata_read_url: str = f"{self.base_url}{meterdata_read_endpoint}"
        self.power_url: str = f"{self.base_url}{power_endpoint}"
        self.hours_report_url: str = f"{self.base_url}{hours_report_endpoint}"
        self.getarchivereport_url: str = f"{self.base_url}{getarchivereport_endpoinf}"
        self.getbackgroundtaskstate_url: str = f"{self.base_url}{getbackgroundtaskstate_endpoint}"

        # Всё что касается сессии
        self.session = requests.Session()
        self.session.verify = False
        self.session.headers.update({
            "Content-Type": "application/json"
        })
        self.username: Optional[str] = None
        self.password: Optional[str] = None
        self.access_token: Optional[str] = None

    def _request(self, method: str, url: str, **kwargs) -> dict:
        """
        Универсальный метод для выполнения HTTP-запросов с обработкой ошибок.

        Args:
            method (str): HTTP-метод ('GET', 'POST', 'PUT', 'DELETE' и т.д.)
            url (str): URL для запроса
            **kwargs: Дополнительные параметры requests (params, json, data, headers и т.д.)

        Returns:
            dict: Распарсенный JSON-ответ

        Raises:
            requests.exceptions.HTTPError: При статусе 4xx/5xx
        """
        response = self.session.request(method.upper(), url, **kwargs)
        response.raise_for_status()
        try:
            return response.json()
        except requests.exceptions.JSONDecodeError:
            return response
    
    
    def restart_session(self) -> None:
        """Рестарт сессии для случая ошибки с паралельным входом"""
        
        self.session = requests.Session()
        self.session.verify = False
        self.session.headers.update({
            "Content-Type": "application/json"
        })
        self.access_token: Optional[str] = None
        
    
    def login(self) -> bool:
        """
        Выполняет вход и получает токены.

        :param username: Имя пользователя
        :param password: Пароль
        :return: True при успешной авторизации, иначе False
        """
        
        payload = {
            "username": self.username,
            "password": self.password,
            "tokens": None
        }

        try:
            data = self._request("POST", self.login_url, json=payload)
        except requests.exceptions.RequestException as e:
            print(f"Ошибка при запросе логина: {e}")
            if hasattr(e, 'response') and e.response is not None:
                print(f"Ответ сервера: {e.response.text}")
            return False

        # Извлекаем токены из ответа
        access_token = data.get("tokens").get("accessToken")
        if not access_token:
            print(f"Не удалось найти access_token в ответе сервера: {data=}")
            return False
        
        self.user_id = data.get("userId", None)

        self.access_token = access_token
        # Устанавливаем заголовок Authorization для всех последующих запросов
        self.session.headers.update({
            "Authorization": f"Bearer {self.access_token}"
        })
        return True
    
    def authorized(self) -> bool:
        """Проверяет наличия токена авторизации"""
        
        if "Authorization" in self.session.headers:
            if "Bearer" in self.session.headers.get("Authorization"):
                return True
            else:
                print("Заголовок авторизации есть, токена нет")
                print(self.session.headers.get("Authorization"))
        else:
            print("Заголовка авторизации нет")
        return False
    
    @staticmethod
    def relogin(func, *args, **kwargs):
        """Обертка для перелогина"""
        
        def wrapper(self, *args, **kwargs):
            if not self.authorized():
                self.login()
            try:
                return func(self, *args, **kwargs)
            except requests.exceptions.HTTPError as e:
                print("Ошибка при запросе")
                if e.response.status_code == 401:
                    print("Отсутствует авторизация, пересоздаём сессию")
                    self.restart_session()
                    self.login()                    
                    return func(self, *args, **kwargs)
                else:
                    print(e.response.status_code)
                    print(e)
                    raise
        return wrapper
    
    def fetch_all_data(self, meter_num: str) -> Meter:
        """Сбор всех нужных данных по счетчику"""
        
        instance = self.get_instances(meter_num)
        instance_id = instance["instance_id"]
        instance_info = self.get_instance_info(instance_id)
        meterdata = self.get_meterdata_read(instance_id)
        
        meter = Meter(
            meter_num = meter_num,
            instance_id = instance_id,
            model = instance["meter_model"],
            routes = instance["meter_routes"],
            address = instance_info["address"],
            contract_num = instance_info["account_id"],
            full_path = instance_info["full_path"],
            
            # Показания
            meter_data_datetime = meterdata["register_datetime"],
            t0plus = meterdata["fine_meter_values"]["A+"]["TO"]["value"],
            t1plus = meterdata["fine_meter_values"]["A+"]["T1"]["value"],
            t2plus = meterdata["fine_meter_values"]["A+"]["T2"]["value"],
            t0minus = meterdata["fine_meter_values"]["A-"]["TO"]["value"],
            t1minus = meterdata["fine_meter_values"]["A-"]["T1"]["value"],
            t2minus = meterdata["fine_meter_values"]["A-"]["T2"]["value"],
            )
        
        return meter

    @relogin
    def fetch_instances(self, meter_num: str) -> dict | None:
        """Выполняет POST-запрос к API для получения id, модели счетчика и маршрутов соеденения по номеру прибора учета"""
        
        payload = {
        "classId": -1646,
        "userCustomized": False,
        "options": {
            "take": "2",
            "sort": '[{"selector":"id","desc":false}]',
            "filter": f'["-1494","contains","{meter_num}"]'  # подставляем номер прибора
            }
        }
            
        return self._request("POST", self.get_instances_url, json=payload)
        
    def extract_instances(self, json_data: dict) -> dict:
        """Парсит JSON-ответ и извлекает id, модель счетчика и маршруты соеденения"""
        
        meter_data = json_data.get("data")
        
        if not meter_data:
            raise ValueError("Прибора учета не существует\nПопробуйте убрать первый 0 в номере прибора учета")
        
        if len(meter_data) > 1:
            raise ValueError("Найдено более одного прибора учета\nПопробуйте уточнить поиск")
        
        data = meter_data[0]
        
        if not data:
            print("Не нашли основные данные прибора учета")
            return None
        
        instance_id = str(data.get('-8295').get('id'))
        meter_model = data.get('-56855')
        meter_routes = [item.get('caption') for item in data.get('-3134')]
        
        res = {
            "instance_id": instance_id,
            "meter_model": meter_model,
            "meter_routes": meter_routes,
            }
        
        return res
    
    def get_instances(self, meter_num: str) -> dict | None:
        """Получает и вытаскивает instance_id, модель, маршруты прибора учёта по его номеру"""
        
        raw_data = self.fetch_instances(meter_num)
        extracted_data = self.extract_instances(raw_data)
        return extracted_data
        
    @relogin
    def fetch_instance_info(self, meter_id: str):
        """Выполняет GET-запрос к API для получения лицевого счёт и адреса точки учёта по id прибора учета"""
        
        params = {"instanceId": meter_id}
        return self._request("GET", self.get_instance_info_url, params=params)

    
    def extract_instance_info(self, json_data: dict):
        """Парсит JSON-ответ и извлекает лицевой счёт и адрес точки учёта"""
                
        instance = json_data.get("instance")
        account_id = instance.get("-10024")[0].get("caption")
        full_path = instance.get("-13379")
        address = full_path.split("/")[-1]
        
        res = {
            "account_id": account_id,
            "address": address,
            "full_path": full_path,
            }
        
        return res
        
    def get_instance_info(self, meter_id: str):
        """Получает json и вытаскивает лицевой счёт и адрес точки учёта"""
        
        raw_data = self.fetch_instance_info(meter_id)
        extracted_data = self.extract_instance_info(raw_data)
        return extracted_data
    
    @relogin
    def fetch_meterdata_read(self, instance_id: str):
        """
        Получение текущих последних показаний прибора учета.
        Используется фильтр "Самарские РС - Показания текущие общие и 2-х зонные 4 канала".
        """
        
        now = datetime.now().isoformat(timespec='milliseconds') # Что-то типа "2026-04-29T18:00:00.123"
        
        payload = {
            "classifierId": 2481,
            "instancesIds": [instance_id],
            "parameters": [-2139, 4726239, 4726797, -1973, 4726597, -2143, 4726253, 4726811, -2141, 4726243, 4726801, 4727155],
            "start": now,
            "finish": now,
            "sources": [[-3718]],
            "requireRatio": False,
            "requireLoses": False
        }
        
        return self._request("POST", self.meterdata_read_url, json=payload)
    
    def extract_meterdata_read(self, json_data: dict):
        """Парсит JSON-ответ и извлекает дату последних показаний и сами показания прибора учета"""
        
        # Извлекаем ключ: "Энергия А+ текущая, Тарифная зона \"День Двухзонный\""
        # Значения: "14167570.0" и "2025-09-24T06:31:08.498"
        meter_values = {
            value["parameter"]["caption"]: (value["values"][0]["value"], value["values"][0]["registerDt"])
            for value in json_data[0].get("parametersData")
            }
        
        def isfloat(float_str):
            """Функция проверки строки на float"""
            try:
                float(float_str)
                return True
            except TypeError:
                return False
            
        def datetime_extracter(v: str) -> datetime:
            dt_part = v.split('.')[0] # "2026-04-29T07:01:16"
            dt = datetime.strptime(dt_part, "%Y-%m-%dT%H:%M:%S")
            return dt
        
        # Меняем строки во float
        meter_values = {
            key: (round(float(meter_values[key][0] / 1000), 2), meter_values[key][1])
            for key in meter_values.keys()
            if isfloat(meter_values[key][0])
            }
        
        # Трансформируем полученный json
        fine_meter_values = {
            "A+": {
                "TO": {"value": None, "datetime": None},
                "T1": {"value": None, "datetime": None},
                "T2": {"value": None, "datetime": None},
                },
            "A-": {
                "TO": {"value": None, "datetime": None},
                "T1": {"value": None, "datetime": None},
                "T2": {"value": None, "datetime": None},
                },
            }
        
        a_plus = "Энергия А+ текущая"
        t1_a_plus = "Энергия А+ текущая, Тарифная зона \"День Двухзонный\""
        t2_a_plus = "Энергия А+ текущая, Тарифная зона \"Ночь Двухзонный\""
        a_minus = "Энергия А- текущая"
        t1_a_minus = "Энергия А- текущая, Тарифная зона \"День Двухзонный\""
        t2_a_minus = "Энергия А- текущая, Тарифная зона \"Ночь Двухзонный\""
        
        
        if a_plus in meter_values:
            fine_meter_values["A+"]["TO"]["value"] = meter_values[a_plus][0]
            fine_meter_values["A+"]["TO"]["datetime"] = datetime_extracter(meter_values[a_plus][1])
    
        if t1_a_plus in meter_values:
            fine_meter_values["A+"]["T1"]["value"] = meter_values[t1_a_plus][0]
            fine_meter_values["A+"]["T1"]["datetime"] = datetime_extracter(meter_values[t1_a_plus][1])
        
        if t2_a_plus in meter_values:
            fine_meter_values["A+"]["T2"]["value"] = meter_values[t2_a_plus][0]
            fine_meter_values["A+"]["T2"]["datetime"] = datetime_extracter(meter_values[t2_a_plus][1])
    
        if a_minus in meter_values:
            fine_meter_values["A-"]["TO"]["value"] = meter_values[a_minus][0]
            fine_meter_values["A-"]["TO"]["datetime"] = datetime_extracter(meter_values[a_minus][1])
        
        if t1_a_minus in meter_values:
            fine_meter_values["A-"]["T1"]["value"] = meter_values[t1_a_minus][0]
            fine_meter_values["A-"]["T1"]["datetime"] = datetime_extracter(meter_values[t1_a_minus][1])
        
        if t2_a_minus in meter_values:
            fine_meter_values["A-"]["T2"]["value"] = meter_values[t2_a_minus][0]
            fine_meter_values["A-"]["T2"]["datetime"] = datetime_extracter(meter_values[t2_a_minus][1])
            
        #return fine_meter_values
        
        @staticmethod
        def define_datetime(fine_meter_values: dict, direction: str):
            """
            Определяет какое из значений показаний принимать за истину.
            Пирамида такая охиренная программа, что может данные в колонках TO T1 T2 могут быть на разные даты
            И не всегда у нас T1 + T2 == TO
            И вообще T1 T2 TO могут быть с разной актуальностью данных.
            Задача брать самые актуальные данные
            Возвращает дату выбранных показаний
            """
            # Если везде None пропускаем
            if (not fine_meter_values[direction]["TO"]["datetime"] and
            not fine_meter_values[direction]["T1"]["datetime"] and
            not fine_meter_values[direction]["T2"]["datetime"]):
                values_datetime = None
            # Если есть только TO
            elif ((fine_meter_values[direction]["TO"]["datetime"] and not fine_meter_values[direction]["T1"]["datetime"]) or
            (fine_meter_values[direction]["TO"]["datetime"] and not fine_meter_values[direction]["T2"]["datetime"])):
                values_datetime = fine_meter_values[direction]["TO"]["datetime"]
            # Если есть только T1 и T2
            elif ((fine_meter_values[direction]["T1"]["datetime"] and fine_meter_values[direction]["T2"]["datetime"]) and
            not fine_meter_values[direction]["TO"]["datetime"]):
                fine_meter_values[direction]["TO"]["value"] = round(fine_meter_values[direction]["T1"]["value"] + fine_meter_values[direction]["T2"]["value"], 2)
                fine_meter_values[direction]["TO"]["datetime"] = fine_meter_values[direction]["T2"]["datetime"]
                values_datetime = fine_meter_values[direction]["T2"]["datetime"]
            # Если TO - T1 > 24ч или TO - T2 > 24ч
            elif (fine_meter_values[direction]["TO"]["datetime"] - fine_meter_values[direction]["T1"]["datetime"] > timedelta(hours=24) or
            fine_meter_values[direction]["TO"]["datetime"] - fine_meter_values[direction]["T2"]["datetime"] > timedelta(hours=24)):
                fine_meter_values[direction]["T1"]["datetime"] = None
                fine_meter_values[direction]["T2"]["datetime"] = None
                fine_meter_values[direction]["T1"]["value"] = None
                fine_meter_values[direction]["T2"]["value"] = None
                values_datetime = fine_meter_values[direction]["TO"]["datetime"]
            # Если T1 > TO и T2 > TO и |T1 - T2| < 24ч
            elif abs(fine_meter_values[direction]["T1"]["datetime"] - fine_meter_values[direction]["T2"]["datetime"] < timedelta(hours=24)):
                fine_meter_values[direction]["TO"]["value"] = round(fine_meter_values[direction]["T1"]["value"] + fine_meter_values[direction]["T2"]["value"], 2)
                fine_meter_values[direction]["TO"]["datetime"] = fine_meter_values[direction]["T2"]["datetime"]
                values_datetime = fine_meter_values[direction]["T2"]["datetime"]
            else:
                raise ValueError("Ни одно условие выбора показаний не подходит")
            
            return values_datetime
        
        a_plus_datetime = define_datetime(fine_meter_values, "A+")
        a_minus_datetime = define_datetime(fine_meter_values, "A-")
        
        if not a_plus_datetime and not a_minus_datetime:
            values_datetime = None
        elif a_plus_datetime and not a_minus_datetime:
            values_datetime = a_plus_datetime
        elif a_minus_datetime and not a_plus_datetime:
            values_datetime = a_minus_datetime
        elif a_plus_datetime > a_minus_datetime:
            values_datetime = a_plus_datetime
        else:
            values_datetime = a_minus_datetime
        
        if values_datetime:
            formatted_values_datetime = values_datetime.strftime("%d.%m.%Y %H:%M")
        else:
            formatted_values_datetime = None
        
        # Результат
        res = {
            "register_datetime": formatted_values_datetime,
            "fine_meter_values": fine_meter_values,
            }
        return res
    
    def get_meterdata_read(self, instance_id: str) -> dict:
        """Получает и обрабатывает данные прибора учета"""
        raw_data = self.fetch_meterdata_read(instance_id)
        extracted_data = self.extract_meterdata_read(raw_data)
        return extracted_data
        
    @relogin
    def fetch_meter_daily_data(self,
                          instance_id: str,
                          start_date: datetime,
                          finish_date: datetime,
                          output_path: str,
                          ):
        """
        Получение показаний прибора учета на начало суток за определенный диапазон
        В пирамиде используем фильтр "Самарские РС - Показания на начало суток общие и 2-х зонные А+"
        """
        
        start_date = start_date.isoformat(timespec='milliseconds')
        finish_date = finish_date.isoformat(timespec='milliseconds')
        payload = {
            "classifierId": 2481,
            "instancesIds": [instance_id],
            "parameters": [-2161, 4726233, 4726791],
            "start": start_date,
            "finish": finish_date,   # по заданию обе даты - текущее время
            "sources": [[-21332], [-3718], [-39224], [-3720], [-3722], [-3724], [-3726]],
            "requireRatio": False,
            "requireLoses": False
        }
        headers = {'No-Limit': 'true'}
        return self._request("POST", self.meterdata_read_url, json=payload, headers=headers)
    
    def create_meter_daily_data_report(self,
                                       instance_id: str,
                                       start_date: datetime,
                                       finish_date: datetime,
                                       output_path: str,
                                       ) -> None:
        """Создаёт файл с показаниям на начало суток за определенный период в формате xlsx"""
        json_data = self.fetch_meter_daily_data(instance_id, start_date, finish_date, output_path)
        meter_caption = json_data[0]["pointWithMeter"]["meter"]["caption"]
        file_output_title = f"Показания на начало суток по {meter_caption}.xlsx"
        full_output_path = Path(output_path) / file_output_title
        create_excel_from_json(json_data, full_output_path)
        return full_output_path
        
    @staticmethod
    def extract_ip(text: str) -> str | None:
        """
        Извлечь IP-адрес из строки, где IP представлен в виде трёхзначных групп.
        Пример: '010.010.020.030' -> '10.10.20.30'
        """
        match = re.search(r'(\d+\.\d+\.\d+\.\d+)', text)
        if not match:
            return None
        
        raw_ip = match.group(1)
        return raw_ip
            
            
    def power_test(self, meter_id: str) -> list:
        """Управление нагрузкой. Метод не используется так как нет прав на это действие."""
        
        meters_ids = [meter_id]   # замените на фактические ID
        state = False               # True = включить, False = выключить
        reason = "Тестовое"
        execution_timeout = 3600   # таймаут в секундах

        # Подготовка тела запроса
        payload = {
            "metersId": meters_ids,
            "state": state,
            "reason": reason,
            "executionTimeout": execution_timeout
        }
        
        response = self.session.post(
                self.power_url,
                json=payload,
            )
    
    @relogin
    def task_create_file_report_async(self,
                                 start_dt: datetime,
                                 end_dt: datetime,
                                 classifier_nodes: list = None,
                                 meter: Meter = None,
                                 ):
        """
        Создание задания на формирование почасового отчёта с заданными точками учёта и периодом.
        Отчет в пирамиде: 02.01 Показания и профиль ЭЭ (30 и 60 мин) по точке учета (СРС)
        """

        # Преобразуем переданные точки в значения для ClassifierNodes
        if meter and not classifier_nodes:
            nodes_values = [{"asInstanceLink": {"id": meter.instance_id, "caption": meter.full_path}}]
        elif classifier_nodes and not meter:
            nodes_values = [
                {"asInstanceLink": {"id": node["id"], "caption": node["caption"]}}
                for node in classifier_nodes
            ]
        else:
            raise ValueError(
                f"Некорректный вызов: ожидается ровно один источник данных (classifier_nodes или meter). "
                f"Получено: classifier_nodes = {classifier_nodes}, meter = {meter}."
            )

        start_str = start_dt.isoformat(timespec='milliseconds')
        end_str = end_dt.isoformat(timespec='milliseconds')
        
        payload = payload_builder._build_task_create_file_report_async(start_str, end_str, nodes_values)
        
        return self._request("POST", self.hours_report_url, json=payload)
    
    
    @relogin
    def download_archive_report(self,
                                archive_entry_id: str,
                                output_path: str,
                                meter: Meter,
                                ) -> None:
        """
        Скачивание файла отчёта из архива.
        Сохраняет бинарный ответ сервера в файл.
        """

        payload = {
            "userId": self.user_id,
            "archiveEntryId": archive_entry_id,
            "keepNotification": False,
            "fileName": "02.01 Показания и профиль ЭЭ (30 и 60 мин) по точке учета (СРС).xlsx"
        }
        timestamp = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
        file_name = f"Почасовка {meter.model} №{meter.meter_num} {timestamp}.xlsx"
        response = self._request("POST", self.getarchivereport_url, json=payload)
        full_output_path = f"{output_path}/{file_name}"
        with open(full_output_path, 'wb') as f:
            f.write(response.content)
        return full_output_path
            
            
    @relogin
    def get_background_task_state(self, background_task_id: int, log_type: int = 1) -> dict:
        """
        Получение состояния фоновой задачи.
        Параметры:
            background_task_id: идентификатор фоновой задачи (query-параметр backgroundTaskId)
            log_type: тип лога, по умолчанию 1 (query-параметр logType)
        Возвращает словарь с данными о состоянии задачи.
        """

        params = {
            "backgroundTaskId": background_task_id,
            "logType": log_type
        }
        return self._request("GET", self.getbackgroundtaskstate_url, params=params)
            
    
    def create_file_report_async(self,
                             start_dt: datetime,
                             end_dt: datetime,
                             output_path: str,
                             classifier_nodes: list = None,
                             meter: Meter = None,
                             ) -> None:
        """
        Создание задачи на формирование отчета, проверка статуса отчета, скачивание.
        Отчет по пирамиде 02.01 Показания и профиль ЭЭ (30 и 60 мин) по точке учета (СРС)
        """
    
        task = self.task_create_file_report_async(start_dt, end_dt, meter=meter)
        task_id, archive_entry_id = task["taskId"], task["archiveEntryId"]
        is_completed = self.get_background_task_state(task_id)["isCompleted"]
        
        while not is_completed:
            is_completed = self.get_background_task_state(task_id)["isCompleted"]
                
        return self.download_archive_report(archive_entry_id, output_path, meter)
    
    
backend_client = PyramidApiClient()
