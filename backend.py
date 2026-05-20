from typing import Optional, Dict, Any
import re
import urllib3
from datetime import datetime
import os

import requests

from config import settings


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
        meter_instance_endpoint: str = "/rdinstance/getinstances/",
        meter_route_endpoint: str = "/routes/getroutes/",
        rd_instance_endpoint: str = "/rdinstance/getinstanceinfo/",
        meterdata_endpoint: str = "/meterdata/read/",
        power_endpoint: str = "/loadlimitmanagement/startasynctaskwriteloadstate/",
        
        #params
        timezone_offset: int = -240,
    ):
        """
        Инициализация клиента.

        :param base_url: Базовый URL API (без завершающего слеша)
        :param login_endpoint: Путь к эндпоинту логина (относительно base_url)
        :param timezone_offset: Смещение часового пояса в минутах (по умолчанию -240)
        """
        self.base_url = base_url.rstrip('/')
        self.login_url = f"{self.base_url}{login_endpoint}?timeZoneOffset=-240"
        self.meter_instance_url = f"{self.base_url}{meter_instance_endpoint}"
        self.meter_route_url = f"{self.base_url}{meter_route_endpoint}"
        self.rd_instance_url = f"{self.base_url}{rd_instance_endpoint}"
        self.meterdata_url = f"{self.base_url}{meterdata_endpoint}"
        self.power_url = f"{self.base_url}{power_endpoint}"
        self.timezone_offset = timezone_offset



        # Храним токен отдельно (на всякий случай)
        self.access_token: Optional[str] = None
        
        self.username = settings.PYRAMID_USERNAME
        self.password = settings.PYRAMID_PSW

    def _build_login_url(self) -> str:
        """Добавляет параметр timeZoneOffset к URL логина."""
        return f"{self.login_url}?timeZoneOffset={self.timezone_offset}"
    
    
    def create_session(self):
        """Создаём аргументы для сесии"""
        # Сессия для поддержки кук и переиспользования заголовков
        self.session = requests.Session()
        self.session.verify = False
        # Базовые заголовки (можно расширить при необходимости)
        self.session.headers.update({
            "Content-Type": "application/json"
        })
        

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
        
        self.create_session()

        try:
            response = self.session.post(
                self.login_url,
                json=payload
            )
            response.raise_for_status()  # выбросит исключение при статусе 4xx/5xx
        except requests.exceptions.RequestException as e:
            print(f"Ошибка при запросе логина: {e}")
            if hasattr(e, 'response') and e.response is not None:
                print(f"Ответ сервера: {e.response.text}")
            return False

        # Извлекаем токены из ответа (предполагаем структуру, адаптируйте под реальный API)
        data = response.json()
        access_token = data.get("tokens").get("accessToken")
        if not access_token:
            print("Не удалось найти access_token в ответе сервера.")
            print(f"Ответ: {data}")
            return False

        self.access_token = access_token
        # Устанавливаем заголовок Authorization для всех последующих запросов
        self.session.headers.update({
            "Authorization": f"Bearer {self.access_token}"
        })
        return True
    
    
    def authorized(self) -> bool:
        """Проверяем наличия токена авторизации"""
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
    def get_meter_instance_data(self, meter_num) -> dict | None:
        """Запрос основных данных прибора учета"""
        
        payload = {
        "classId": -1646,
        "userCustomized": False,
        "options": {
            "take": "1",
            "sort": '[{"selector":"id","desc":false}]',
            "filter": f'["-1494","contains","{meter_num}"]'  # подставляем номер прибора
        }
    }
            
        response = self.session.post(
                self.meter_instance_url,
                json=payload
            )
        response.raise_for_status()  # выбросит исключение при статусе 4xx/5xx
        
        data = response.json().get("data")[0]
        
        if not data:
            print("Не нашли основные данные прибора учета")
            return None
        
        instance_id = data.get('-8295').get('id')
        meter_model = data.get('-56855')
        meter_routes = [item.get('caption') for item in data.get('-3134')]
        #address = data.get("-8295").get("caption").split("\\")[2:-1]
        #address = ", ".join(address)
        
        res = {
            "instance_id": instance_id,
            "meter_model": meter_model,
            "meter_routes": meter_routes,
            #"address": address,
            }
        
        return res
    
    @relogin
    def get_rd_instance_data(self, meter_id):
        """Получение адреса и лицеового счета точки учета"""
            
        payload = f"instanceId={meter_id}"
        
        response = self.session.get(
            self.rd_instance_url,
            params={"instanceId": meter_id}
            )
        response.raise_for_status()  # выбросит исключение при статусе 4xx/5xx
        
        instance = response.json().get("instance")
        account_id = instance.get("-10024")[0].get("caption")
        address = instance.get("-13379").split("/")[-1]
        
        res = {
            "account_id": account_id,
            "address": address,
            }
        
        return res
    
    @relogin
    def get_meter_data(self, instance_id):
        """Получение последних показаний прибора учета"""
        
        now = datetime.now().isoformat(timespec='milliseconds')
        # now будет например "2026-04-29T18:00:00.123"
        
        payload = {
            "classifierId": 2481,
            "instancesIds": [instance_id],
            #"parameters": [4727155, 4726253, 4726811, 4726243, 4726801, 4726239, 4726797, 4726597],
            "parameters": [-2139, 4726239, 4726797, -1973, 4726597, -2143, 4726253, 4726811, -2141, 4726243, 4726801, 4727155],
            "start": now,
            "finish": now,   # по заданию обе даты - текущее время
            "sources": [[-3718]],
            "requireRatio": False,
            "requireLoses": False
        }
        
        response = self.session.post(
            self.meterdata_url,
            json=payload
        )
        response.raise_for_status()
        
        meter_values = {
            value["parameter"]["caption"]: value["values"][0]["value"]
            for value in response.json()[0].get("parametersData")
            }
        
        def isfloat(float_str):
            try:
                float(float_str)
                return True
            except TypeError:
                return False
            
        
        
        meter_values = {
            key: round(float(meter_values[key] / 1000), 2)
            for key in meter_values.keys()  # или просто for key in meter_values
            if isfloat(meter_values[key])
            }
        
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
        
        for value in meter_values:
            if "Энергия А+ текущая, Тарифная зона \"День Двухзонный\"" in value:
                fine_meter_values["A+"]["T1"] = meter_values[value]
            elif "Энергия А+ текущая, Тарифная зона \"Ночь Двухзонный\"" in value:
                fine_meter_values["A+"]["T2"] = meter_values[value]
            elif "Энергия А+ текущая" in value:
                fine_meter_values["A+"]["TO"] = meter_values[value]
            elif "Энергия А- текущая, Тарифная зона \"День Двухзонный\"" in value:
                fine_meter_values["A-"]["T1"] = meter_values[value]
            elif "Энергия А- текущая, Тарифная зона \"Ночь Двухзонный\"" in value:
                fine_meter_values["A-"]["T2"] = meter_values[value]
            elif "Энергия А- текущая" in value:
                fine_meter_values["A-"]["TO"] = meter_values[value]
                
        #fine_meter_values["A+"]["TO"] = round(float(fine_meter_values["A+"]["T1"] + fine_meter_values["A+"]["T2"]), 2)
        #fine_meter_values["A-"]["TO"] = round(float(fine_meter_values["A-"]["T1"] + fine_meter_values["A-"]["T2"]), 2)
        
        meter_value_register_datetime = response.json()[0]["parametersData"][0]["values"][0]["registerDt"]
        dt_part = meter_value_register_datetime.split('.')[0] # "2026-04-29T07:01:16"
        dt = datetime.strptime(dt_part, "%Y-%m-%dT%H:%M:%S")
        formatted = dt.strftime("%d.%m.%Y %H:%M")
        
        res = {
            "register_datetime": formatted,
            "fine_meter_values": fine_meter_values,
            }
        
        return res
        
        
    @relogin
    def _get_meter_route_data(self, meter_id):
        """Запрос данных маршрута прибора учета"""
            
        payload = [meter_id]
        
        
        response = self.session.post(
                self.meter_route_url,
                json=payload
            )
        response.raise_for_status()  # выбросит исключение при статусе 4xx/5xx
        
        data = response.json()
        if data:
            print("Получили данные маршрута прибора учета")
            return data[0]
        else:
            return None
        
    def get_meter_route_captions(self, meter_num: str) -> list:
        """Запрос ip прибора учета"""
        
        meter_instance = self._get_meter_instance_data(meter_num)
        if not meter_instance:
            print("Не нашел прибор учета")
            return []
        
        meter_id = meter_instance.get("id")
        if not meter_id:
            print("Не нашел ID прибора учета")
            return []
        
        meter_route = self._get_meter_route_data(meter_id)
        if meter_route:
            meter_routes = meter_route.get("routes")
            if meter_routes:
                meter_routes_captions = [meter_route.get("caption") for meter_route in meter_routes]
                return meter_routes_captions
            else:
                print("В маршруте нет данных об IP")
                return []
        else:
            print("Не найдены данные маршрута по данному ПУ")
            return []
        
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


    def get_meter_routes(self, meter_num: str) -> list:
        """Формируем список параметров для подключений на GUI"""
        res = []
        note = None
        meter_route_captions = self.get_meter_route_captions(meter_num)
        for i in meter_route_captions:
            print(i)
            
            
    def power_test(self, meter_id: str) -> list:
        """Управление нагрузкой"""
        
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
                json=payload
            )
        
        print(response.text)
                    
                    
# Пример использования
if __name__ == "__main__":
    # Создаём клиент
    client = PyramidApiClient()
    client.login()
    
    #print(client.get_meter_instance_data("04101959"))
    #print(client.get_rd_instance_data("19609718"))
    #print(client.get_meter_data("19609718"))
    print(client.get_meter_data("20156606"))
    #print(client.power_test("20844272")) #пу 021250471434
    #https://s00-pml-web1.hq.vlmrk.corp:8080/api/v1/rdinstance/getinstanceinfo/?instanceId=19609718