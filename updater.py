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
    try:
        headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'}
        response = requests.get(
            url,
            stream=True,
            verify=False,
            headers=headers,
            )
        response.raise_for_status()
    except Exception:
        # Основная ссылка недоступна (например, GitHub заблокирован в корп. сети) — пробуем запасной сервер
        response = requests.get(settings.FALLBACK_EXE_URL, stream=True)
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
        
        # Запускаем установщик и выходим
        subprocess.Popen([filepath])
        sys.exit(0)

    except Exception as e:
        # В случае ошибки можно передать её в GUI
        raise e
    

def download_and_install_v2(url, progress_callback):
    
    class TLS13Adapter(HTTPAdapter):
        def init_poolmanager(self, *args, **kwargs):
            ctx = create_urllib3_context()
            ctx.minimum_version = ssl.TLSVersion.TLSv1_3
            ctx.maximum_version = ssl.TLSVersion.TLSv1_3
            ctx.check_hostname = False
            ctx.verify_mode = ssl.CERT_NONE
            kwargs['ssl_context'] = ctx
            return super().init_poolmanager(*args, **kwargs)
    
    try:
        
        session = requests.Session()
        session.proxies = {
            'http': 'http://ngfw.samara.vlmrk.corp:8090',
            'https': 'http://ngfw.samara.vlmrk.corp:8090',
        }
        session.mount('https://', TLS13Adapter())
        
        response = session.get(
            url,
            stream=True,
            verify=False,
            )
        response.raise_for_status()

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
        
        # Запускаем установщик и выходим
        #subprocess.Popen([filepath])
        sys.exit(0)

    except Exception as e:
        # В случае ошибки можно передать её в GUI
        raise e




def download_via_curl(url):
    import os, sys, subprocess

    filename = url.split('/')[-1]
    filepath = os.path.join(os.getcwd(), filename)

    env = os.environ.copy()
    env['http_proxy'] = 'http://ngfw.samara.vlmrk.corp:8090'
    env['https_proxy'] = env['http_proxy']

    # Блокирующий вызов curl (без прогресс-бара, просто ждёт)
    subprocess.run([
        'curl', '-L', '-k', '--tlsv1.3',
        '--connect-timeout', '60', '--max-time', '600',
        '-o', filepath, url
    ], env=env, check=True)

    # Запускаем скачанный файл и выходим из текущей программы
    subprocess.Popen([filepath])
    sys.exit(0)
    
    
if __name__ == '__main__':
    data = check_update()
    url = data["url"]
    download_via_curl(url)
    