import os
import threading
import subprocess
import time
import platform


class PingWorker:
    """
    Запускает ping в отдельном потоке.
    Отправляет одиночные ping-пакеты до первого успеха,
    но не более max_attempts попыток.
    """
    def __init__(self, ip, max_attempts=50, attempt_callback=None, finished_callback=None):
        """
        :param ip: IP-адрес для пинга
        :param max_attempts: максимальное количество попыток (по умолчанию 5)
        :param attempt_callback: вызывается при каждой попытке (номер_попытки, всего_попыток)
        :param finished_callback: вызывается по окончании (success_any)
        """
        self.ip = ip
        self.max_attempts = max_attempts
        self.attempt_callback = attempt_callback
        self.finished_callback = finished_callback
        self.process = None
        self.stop_flag = False

    def start(self):
        self.thread = threading.Thread(target=self._run, daemon=True)
        self.thread.start()

    def stop(self):
        """Останавливает текущий пинг, если он ещё выполняется."""
        self.stop_flag = True
        if self.process and self.process.poll() is None:
            self.process.terminate()

    def _run(self):
        system = platform.system().lower()
        for attempt in range(1, self.max_attempts + 1):
            if self.stop_flag:
                break

            # Вызываем callback о начале попытки
            if self.attempt_callback:
                self._safe_callback(self.attempt_callback, attempt, self.max_attempts)

            # Формируем команду ping для одного пакета
            if system == "windows":
                # -n 1 - один пакет, -w 1000 - таймаут 1 секунда
                cmd = ["ping", "-n", "1", "-w", "1000", self.ip]
            else:
                # -c 1 - один пакет, -W 1 - таймаут 1 секунда
                cmd = ["ping", "-c", "1", "-W", "1", self.ip]

            try:
                self.process = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                                                text=True, creationflags=subprocess.CREATE_NO_WINDOW)
                self.process.wait(timeout=2)  # таймаут на всякий случай
                success = (self.process.returncode == 0)
                self.process = None
            except Exception as e:
                print(f"Ping error for {self.ip}: {e}")
                success = False

            if success:
                # Успешный пинг
                if self.finished_callback:
                    self._safe_callback(self.finished_callback, True)
                return

            # Небольшая пауза между попытками (опционально)
            if attempt < self.max_attempts and not self.stop_flag:
                time.sleep(0.5)

        # Все попытки исчерпаны, успеха не было
        if self.finished_callback:
            self._safe_callback(self.finished_callback, False)

    def _safe_callback(self, callback, *args):
        """Вызов callback в главном потоке через root.after."""
        def wrapper():
            callback(*args)
        import tkinter as tk
        try:
            root = tk._default_root
            if root:
                root.after(0, wrapper)
            else:
                wrapper()
        except:
            wrapper()