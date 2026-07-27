import requests
from packaging.version import Version
from version import __version__ as current_version
from config import settings
import subprocess
import os
import sys
import subprocess, re, threading
from requests.adapters import HTTPAdapter
from urllib3.util.ssl_ import create_urllib3_context
import ssl
import time

def check_update():
    try:
        r = requests.get(settings.GITHUB_API, timeout=5)
        data = r.json()

        latest_version = data["tag_name"].lstrip("v")  # "v1.2.3" → "1.2.3"

        if Version(latest_version) > Version(current_version):
            # Берём ссылку на exe из assets
            url = data["assets"][0]["browser_download_url"]
            changelog = data["body"]  # текст релиза — готовый changelog
            return {"version": latest_version, "url": url, "changelog": changelog}
    except Exception:
        pass
    return None

def download_and_install(progress_callback=None, status_callback=None):
    """
    Загружает обновление. Вызывает:
        status_callback(status_message, attempt_number)
        progress_callback(percent, downloaded_bytes, total_bytes)
    Возвращает путь к скачанному файлу.
    """
    reconnect_counter = 1
    response = None

    # Цикл подключения
    while True:
        try:
            if status_callback:
                status_callback(f"Попытка {reconnect_counter}...", reconnect_counter)
            response = requests.get(settings.FALLBACK_EXE_URL, stream=True, verify=False)
            if response.status_code == 200:
                if status_callback:
                    status_callback("Соединение установлено", 0)  # сигнал успеха
                break
            else:
                if status_callback:
                    status_callback(f"Сервер вернул {response.status_code}", reconnect_counter)
                reconnect_counter += 1
                time.sleep(5)
        except Exception as e:
            if status_callback:
                status_callback(f"Ошибка: {e}", reconnect_counter)
            reconnect_counter += 1
            time.sleep(5)

    url = settings.FALLBACK_EXE_URL
    try:
        total_size = int(response.headers.get('content-length', 0))
        downloaded_size = 0
        filename = url.split('/')[-1]
        filepath = os.path.join(os.getcwd(), filename)

        with open(filepath, 'wb') as f:
            for chunk in response.iter_content(chunk_size=8192):
                if chunk:
                    f.write(chunk)
                    downloaded_size += len(chunk)
                    if progress_callback:
                        percent = (downloaded_size / total_size) * 100 if total_size > 0 else 0
                        progress_callback(percent, downloaded_size, total_size)

        if progress_callback:
            progress_callback(100, downloaded_size, total_size)

        return filepath
    except Exception as e:
        raise e
    