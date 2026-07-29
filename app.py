import json
import logging
import os
import pickle
import re
import subprocess
import sys
import threading
from datetime import datetime

import webview

from backend import backend_client
from utils.pinger import PingWorker
import updater
from version import __version__
from config import settings

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    datefmt='%H:%M:%S'
)
logger = logging.getLogger(__name__)

IP_RE = re.compile(r'\b(?:[0-9]{1,3}\.){3}[0-9]{1,3}\b')


def resource_path(rel):
    """Работает и из исходников, и из собранного PyInstaller onefile."""
    base = getattr(sys, "_MEIPASS", os.path.dirname(os.path.abspath(__file__)))
    return os.path.join(base, rel)


class Api:
    def __init__(self):
        self._window = None
        self._client = backend_client
        self.current_meter = None
        self.current_instance_id = None
        self.workers = {}          # row_id -> PingWorker

    # -- мост в JS -------------------------------------------------
    def _emit(self, event, payload=None):
        """Вызов JS-функции из любого потока."""
        if not self._window:
            return
        try:
            self._window.evaluate_js(
                f"window.on{event}({json.dumps(payload, ensure_ascii=False, default=str)})")
        except Exception as e:
            logger.debug(f"emit {event} failed: {e}")

    # -- учётные данные --------------------------------------------
    def _load_credentials(self):
        if os.path.exists(settings.CRED_FILE):
            try:
                with open(settings.CRED_FILE, 'rb') as f:
                    data = pickle.load(f)
                    return data.get('login'), data.get('password')
            except Exception as e:
                logger.error(f"Ошибка загрузки сохранённых данных: {e}")
        return None, None

    def _save_credentials(self, login, password):
        with open(settings.CRED_FILE, 'wb') as f:
            pickle.dump({'login': login, 'password': password}, f)

    # -- вызывается из JS ------------------------------------------
    def bootstrap(self):
        """Первый вызов из index.html: версия + попытка автовхода."""
        threading.Thread(target=self._check_update, daemon=True).start()
        login, password = self._load_credentials()
        if login and password:
            threading.Thread(target=self._login, args=(login, password, False),
                             daemon=True).start()
            return {"version": __version__, "state": "logging_in", "login": login}
        return {"version": __version__, "state": "need_login"}

    def login(self, login, password, remember=True):
        threading.Thread(target=self._login, args=(login, password, remember),
                         daemon=True).start()

    def _login(self, login, password, remember):
        self._emit("Status", {"text": "Выполняется вход…"})
        try:
            self._client.username = login
            self._client.password = password
            if self._client.login():
                if remember:
                    self._save_credentials(login, password)
                self._emit("Auth", {"ok": True, "login": login})
                self._emit("Status", {"text": "Готов"})
            else:
                self._emit("Auth", {"ok": False, "error": "Неверный логин или пароль"})
                self._emit("Status", {"text": "Вход не выполнен"})
        except Exception as e:
            logger.exception(f"Исключение при авторизации: {e}")
            self._emit("Auth", {"ok": False, "error": f"Не удалось подключиться: {e}"})
            self._emit("Status", {"text": "Нет соединения"})

    def fetch(self, meter_num):
        threading.Thread(target=self._fetch, args=(meter_num,), daemon=True).start()

    def _fetch(self, meter_num):
        self._stop_pings()
        if not self._client.access_token:
            self._emit("Hint", {"text": "Нет активной сессии — войдите заново"})
            return

        self.current_meter = None
        self.current_instance_id = None
        self._emit("Loading", {"on": True})
        self._emit("Status", {"text": "Поиск данных…"})

        try:
            meter = self._client.fetch_all_data(meter_num)
            if not meter:
                self._emit("Meter", None)
                self._emit("Status", {"text": "Ничего не найдено"})
                return

            self.current_meter = meter
            self.current_instance_id = meter.instance_id

            routes = []
            for i, route in enumerate(meter.routes or []):
                ip_match = IP_RE.search(route)
                routes.append({
                    "id": f"r{i}",
                    "text": route,
                    "ip": ip_match.group(0) if ip_match else None,
                })

            self._emit("Meter", {
                "model": meter.model,
                "address": meter.address,
                "fullPath": meter.full_path,
                "account": meter.contract_num,
                "readingsTime": meter.meter_data_datetime,
                "readings": {
                    "A+": {"TO": meter.t0plus, "T1": meter.t1plus, "T2": meter.t2plus},
                    "A-": {"TO": meter.t0minus, "T1": meter.t1minus, "T2": meter.t2minus},
                },
                "routes": routes,
            })
            self._emit("Status", {"text": "Готов"})

            for r in routes:
                self.ping(r["id"], r["ip"])

        except ValueError as e:
            logger.warning(f"Ошибка данных: {e}")
            self._emit("Hint", {"text": str(e)})
            self._emit("Status", {"text": "Ошибка данных"})
        except Exception as e:
            logger.exception(f"Необработанная ошибка в fetch: {e}")
            self._emit("Hint", {"text": f"Ошибка: {e}"})
            self._emit("Status", {"text": "Ошибка выполнения"})
        finally:
            self._emit("Loading", {"on": False})

    # -- пинг ------------------------------------------------------
    def ping(self, row_id, ip):
        if not ip:
            self._emit("Ping", {"id": row_id, "state": "err", "text": "нет IP"})
            return

        old = self.workers.pop(row_id, None)
        if old:
            old.stop()

        self._emit("Ping", {"id": row_id, "state": "wait", "text": "…"})

        def on_attempt(attempt, max_attempts):
            self._emit("Ping", {"id": row_id, "state": "wait",
                                "text": f"{attempt}/{max_attempts}"})

        def on_finished(success):
            self._emit("Ping", {
                "id": row_id,
                "state": "ok" if success else "err",
                "text": "в сети" if success else "нет ответа",
            })
            self.workers.pop(row_id, None)

        worker = PingWorker(ip, max_attempts=50,
                            attempt_callback=on_attempt,
                            finished_callback=on_finished)
        self.workers[row_id] = worker
        worker.start()

    def _stop_pings(self):
        for w in self.workers.values():
            w.stop()
        self.workers.clear()

    # -- выгрузки --------------------------------------------------
    def browse_folder(self):
        result = self._window.create_file_dialog(webview.FOLDER_DIALOG)
        return result[0] if result else None

    def export(self, kind, start, finish, output_dir):
        try:
            start_dt = datetime.strptime(start, "%d.%m.%Y")
            finish_dt = datetime.strptime(finish, "%d.%m.%Y")
        except ValueError:
            return {"ok": False, "error": "Формат даты: ДД.ММ.ГГГГ"}
        if not os.path.isdir(output_dir):
            return {"ok": False, "error": "Такой папки нет"}
        if not self.current_meter:
            return {"ok": False, "error": "Сначала получите данные прибора"}

        threading.Thread(target=self._export,
                         args=(kind, start_dt, finish_dt, output_dir),
                         daemon=True).start()
        return {"ok": True}

    def _export(self, kind, start_dt, finish_dt, output_dir):
        self._emit("Export", {"stage": "running", "kind": kind})
        try:
            if kind == "daily":
                path = self._client.create_meter_daily_data_report(
                    instance_id=self.current_instance_id,
                    start_date=start_dt, finish_date=finish_dt,
                    output_path=output_dir)
            else:
                path = self._client.create_file_report_async(
                    start_dt=start_dt, end_dt=finish_dt,
                    output_path=output_dir, meter=self.current_meter)
            self._emit("Export", {"stage": "done", "path": str(path)})
            self._emit("Status", {"text": f"Отчёт сохранён: {path}"})
        except Exception as e:
            logger.exception(f"Ошибка выгрузки: {e}")
            self._emit("Export", {"stage": "error", "error": str(e)})

    def open_folder(self, path):
        folder = path if os.path.isdir(path) else os.path.dirname(path)
        if os.name == "nt":
            os.startfile(folder)
        else:
            subprocess.Popen(["xdg-open", folder])

    def copy(self, text):
        return text          # копирование делает сам JS через navigator.clipboard

    # -- обновление ------------------------------------------------
    def _check_update(self):
        try:
            info = updater.check_update()
            if info:
                self._emit("Update", {
                    "version": info["version"],
                    "changelog": info["changelog"],
                })
        except Exception as e:
            logger.error(f"Ошибка при проверке обновлений: {e}")

    def start_update(self):
        threading.Thread(target=self._download_update, daemon=True).start()

    def _download_update(self):
        def on_progress(percent, downloaded, total):
            self._emit("UpdateProgress", {
                "percent": round(percent), "downloaded": downloaded, "total": total})

        def on_status(message, attempt):
            self._emit("UpdateStatus", {"message": message, "attempt": attempt})

        try:
            path = updater.download_and_install(progress_callback=on_progress,
                                                status_callback=on_status)
            if path:
                subprocess.Popen([path])
            self._stop_pings()
            self._window.destroy()
        except Exception as e:
            logger.error(f"Ошибка загрузки обновления: {e}")
            self._emit("UpdateStatus", {"message": f"Не удалось загрузить: {e}",
                                        "attempt": -1})

    def minimize(self):
        self._window.minimize()

    def close(self):
        self._stop_pings()
        self._window.destroy()


def main():
    api = Api()
    window = webview.create_window(
        "Простая Пирамида",
        resource_path(os.path.join("ui", "index.html")),
        js_api=api,
        width=920, height=620,
        min_size=(840, 560),
        background_color="#FAFAF9",
    )
    api._window = window
    webview.start(debug=os.environ.get("PYRAMID_DEBUG") == "1")


if __name__ == "__main__":
    main()
