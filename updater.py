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

def download_and_install(url, progress_callback):
    response = requests.get(settings.FALLBACK_EXE_URL, stream=True, verify=False)
    response.raise_for_status()
    url = settings.FALLBACK_EXE_URL
    try:
        total_size = int(response.headers.get('content-length', 0))
        downloaded_size = 0
        
        # Имя файла из URL
        filename = url.split('/')[-1]
        filepath = os.path.join(os.getcwd(), filename)

        with open(filepath, 'wb') as f:
            for chunk in response.iter_content(chunk_size=8192):
                if chunk:
                    f.write(chunk)
                    downloaded_size += len(chunk)
                    if total_size > 0:
                        progress = (downloaded_size / total_size) * 100
                        progress_callback(progress)
        
        if progress_callback:
            progress_callback(100)  # сигнал завершения
        return filepath  # только путь, без запуска

    except Exception as e:
        # В случае ошибки можно передать её в GUI
        raise e
    