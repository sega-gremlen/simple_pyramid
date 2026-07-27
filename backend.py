from typing import Optional, Dict, Any
import re
import urllib3
from datetime import datetime
import os
from pathlib import Path


import requests

from config import settings
from utils.xlsx_exporter import create_excel_from_json


urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)


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
        
        #params
        timezone_offset: int = -240,
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
        self.timezone_offset: int = timezone_offset

        # Всё что касается сессии
        self.session = requests.Session()
        self.session.verify = False
        self.session.headers.update({
            "Content-Type": "application/json"
        })
        self.username: Optional[str] = None
        self.password: Optional[str] = None
        self.access_token: Optional[str] = None

    def _build_login_url(self) -> str:
        """Добавляет параметр timeZoneOffset к URL логина."""
        return f"{self.login_url}?timeZoneOffset={self.timezone_offset}"
    
    
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
        return response.json()
    
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
                    print("Отсутствует авторизация, делаем перелогин")
                    self.login()
                    return func(self, *args, **kwargs)
                raise
        return wrapper

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
        address = instance.get("-13379").split("/")[-1]
        
        res = {
            "account_id": account_id,
            "address": address,
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
        
        meter_values = {
            value["parameter"]["caption"]: value["values"][0]["value"]
            for value in json_data[0].get("parametersData")
            }
        
        def isfloat(float_str):
            """Функция проверки строки на float"""
            try:
                float(float_str)
                return True
            except TypeError:
                return False
        
        # Меняем строки во float
        meter_values = {
            key: round(float(meter_values[key] / 1000), 2)
            for key in meter_values.keys()
            if isfloat(meter_values[key])
            }
        
        # Трансформируем полученный json
        fine_meter_values = {
            "A+": {
                "TO": 0,
                "T1": 0,
                "T2": 0,
                },
            "A-": {
                "TO": 0,
                "T1": 0,
                "T2": 0,
                },
            }
        
        t1_a_plus = "Энергия А+ текущая, Тарифная зона \"День Двухзонный\""
        t2_a_plus = "Энергия А+ текущая, Тарифная зона \"Ночь Двухзонный\""
        a_plus = "Энергия А+ текущая"
        t1_a_minus = "Энергия А- текущая, Тарифная зона \"День Двухзонный\""
        t2_a_minus = "Энергия А- текущая, Тарифная зона \"Ночь Двухзонный\""
        a_minus = "Энергия А- текущая"
        
        if t1_a_plus in meter_values:
            fine_meter_values["A+"]["T1"] = meter_values[t1_a_plus]
            
        if t2_a_plus in meter_values:
            fine_meter_values["A+"]["T2"] = meter_values[t2_a_plus]
            
        if t1_a_minus in meter_values:
            fine_meter_values["A-"]["T1"] = meter_values[t1_a_minus]
            
        if t2_a_minus in meter_values:
            fine_meter_values["A-"]["T2"] = meter_values[t2_a_minus]
        
        # Делаем через сумму потому что бывают разные значения там
        if fine_meter_values["A+"]["T1"] or fine_meter_values["A+"]["T2"]:
            fine_meter_values["A+"]["TO"] = round(fine_meter_values["A+"]["T1"] + fine_meter_values["A+"]["T2"], 2)
        else:
            fine_meter_values["A+"]["TO"] = meter_values[a_plus]
        
        if fine_meter_values["A-"]["T1"] or fine_meter_values["A-"]["T2"]:
            fine_meter_values["A-"]["TO"] = round(fine_meter_values["A-"]["T1"] + fine_meter_values["A-"]["T2"], 2)
        else:
            fine_meter_values["A-"]["TO"] = meter_values[a_minus]
        
        # Извлекаем даты, берем из всех самую последнюю
        datetimes = []
        for parameter_data in json_data[0]["parametersData"]:
            if meter_value_register_datetime := parameter_data["values"][0]["registerDt"]:
                datetimes.append(meter_value_register_datetime)
        max_datetime = max(datetimes)
        dt_part = max_datetime.split('.')[0] # "2026-04-29T07:01:16"
        dt = datetime.strptime(dt_part, "%Y-%m-%dT%H:%M:%S")
        formatted = dt.strftime("%d.%m.%Y %H:%M")
        
        # Результат
        res = {
            "register_datetime": formatted,
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
            "sources": [[-3718]],
            "requireRatio": False,
            "requireLoses": False
        }
        return self._request("POST", self.meterdata_read_url, json=payload)
    
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
        
backend_client = PyramidApiClient()
