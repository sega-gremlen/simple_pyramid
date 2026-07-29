import tkinter as tk
from tkinter import ttk, messagebox, filedialog
import pickle
import os
import re
import logging
import threading
from datetime import datetime, date
import calendar
import subprocess

from backend import backend_client
from utils.pinger import PingWorker
import updater
from version import __version__
from config import settings

# Настройка логирования
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    datefmt='%H:%M:%S'
)
logger = logging.getLogger(__name__)


class PyramidApp:
    def __init__(self):
        self.root = tk.Tk()
        self.root.title("Простая Пирамида")
        self.root.geometry("850x500")
        self.root.resizable(False, False)

        self.client = backend_client
        self.current_user = None
        self.current_instance_id = None
        self.current_meter = None
        self.route_rows = []

        self.create_widgets()
        self.root.after(100, self.initial_login)
        self.root.after(500, self.check_for_updates)
        logger.info("Приложение запущено")

    def start(self):
        self.root.mainloop()

    # ------------------------------------------------------------
    #  Построение интерфейса
    # ------------------------------------------------------------
    def create_widgets(self):
        # Настройка сетки корневого окна
        self.root.grid_rowconfigure(3, weight=1)   # строка с маршрутами будет растягиваться
        self.root.grid_columnconfigure(0, weight=1)

        # Верхняя панель (пользователь + кнопка смены)
        top_frame = tk.Frame(self.root)
        top_frame.grid(row=0, column=0, sticky="ew", padx=10, pady=5)

        self.lbl_user = tk.Label(top_frame, text="Пользователь: не авторизован",
                                 anchor=tk.W, font=("Arial", 9))
        self.lbl_user.pack(side=tk.LEFT, fill=tk.X, expand=True)

        btn_change_user = tk.Button(top_frame, text="Сменить пользователя",
                                    command=self.change_user, bg="#FF9800")
        btn_change_user.pack(side=tk.RIGHT)

        # Рамка параметров поиска
        frame_meter = tk.LabelFrame(self.root, text="Параметры поиска", padx=10, pady=5)
        frame_meter.grid(row=1, column=0, sticky="ew", padx=10, pady=5)

        tk.Label(frame_meter, text="Номер прибора учета (ПУ):").grid(
            row=0, column=0, sticky="w", padx=(0, 10))
        self.entry_meter_num = tk.Entry(frame_meter, width=30)
        self.enable_paste(self.entry_meter_num)
        self.entry_meter_num.grid(row=0, column=1, padx=(0, 10))
        self.entry_meter_num.bind("<Return>", lambda e: self.fetch_meter_data())

        self.btn_get = tk.Button(frame_meter, text="Получить данные",
                                 command=self.fetch_meter_data,
                                 bg="#4CAF50", fg="white", font=("Arial", 10, "bold"))
        self.btn_get.grid(row=0, column=2)

        # Кнопка "Выгрузить подневку"
        self.btn_export = tk.Button(frame_meter, text="Выгрузить подневку",
                                    command=self.open_export_dialog,
                                    bg="#2196F3", fg="white",
                                    font=("Arial", 10, "bold"),
                                    state=tk.DISABLED)
        self.btn_export.grid(row=0, column=3, padx=(10, 0))

        # Кнопка "Выгрузить почасовку"
        self.btn_export_hourly = tk.Button(frame_meter, text="Выгрузить почасовку",
                                           command=self.open_export_hourly_dialog,
                                           bg="#9C27B0", fg="white",
                                           font=("Arial", 10, "bold"),
                                           state=tk.DISABLED)
        self.btn_export_hourly.grid(row=0, column=4, padx=(10, 0))

        # Горизонтальная панель: информация о точке + показания
        main_info_row = tk.Frame(self.root)
        main_info_row.grid(row=2, column=0, sticky="ew", padx=10, pady=5)

        # Левая часть – информация о точке
        self.info_frame = tk.LabelFrame(main_info_row, text="Информация о точке",
                                        padx=10, pady=10)
        self.info_frame.pack(side=tk.LEFT, fill="both", expand=True, padx=(0, 5))

        self.meter_model_var = tk.StringVar(value="—")
        self.address_var = tk.StringVar(value="—")
        self.account_var = tk.StringVar(value="—")

        tk.Label(self.info_frame, text="Тип счетчика:",
                 font=("Arial", 9, "bold")).grid(row=0, column=0, sticky="w", pady=2)
        tk.Label(self.info_frame, textvariable=self.meter_model_var,
                 font=("Arial", 9)).grid(row=0, column=1, sticky="w", padx=(10, 0), pady=2)

        tk.Label(self.info_frame, text="Место установки:",
                 font=("Arial", 9, "bold")).grid(row=1, column=0, sticky="w", pady=2)
        lbl_address = tk.Label(self.info_frame, textvariable=self.address_var,
                               font=("Arial", 9), anchor="w")
        lbl_address.grid(row=1, column=1, sticky="w", padx=(10, 0), pady=2)
        self.lbl_address = lbl_address
        self._full_address = ""

        tk.Label(self.info_frame, text="Лицевой счет:",
                 font=("Arial", 9, "bold")).grid(row=2, column=0, sticky="w", pady=2)
        tk.Label(self.info_frame, textvariable=self.account_var,
                 font=("Arial", 9)).grid(row=2, column=1, sticky="w", padx=(10, 0), pady=2)

        # Правая часть – показания
        self.readings_frame = tk.LabelFrame(main_info_row, text="Показания, кВт·ч",
                                            padx=10, pady=10, width=280)
        self.readings_frame.pack(side=tk.RIGHT, fill="both", padx=(5, 0))

        header_row = tk.Frame(self.readings_frame)
        header_row.pack(fill=tk.X, pady=(0, 5))
        tk.Label(header_row, text="", width=6).pack(side=tk.LEFT)
        self.lbl_a_plus = tk.Label(header_row, text="A+", font=("Arial", 9, "bold"),
                                   anchor="center")
        self.lbl_a_plus.pack(side=tk.LEFT, padx=2, fill=tk.X, expand=True)
        self.lbl_a_minus = tk.Label(header_row, text="A−", font=("Arial", 9, "bold"),
                                    anchor="center")
        self.lbl_a_minus.pack(side=tk.LEFT, padx=2, fill=tk.X, expand=True)

        self.reading_vars = {}
        for tariff in ["TO", "T1", "T2"]:
            row_frame = tk.Frame(self.readings_frame)
            row_frame.pack(fill=tk.X, pady=2)
            tk.Label(row_frame, text=tariff, font=("Arial", 9), width=3,
                     anchor="e").pack(side=tk.LEFT, padx=(0, 2))
            for direction in ["A+", "A-"]:
                var = tk.StringVar(value="—")
                lbl = tk.Label(row_frame, textvariable=var, font=("Arial", 9),
                               width=12, anchor="center", relief=tk.SUNKEN, bd=1)
                lbl.pack(side=tk.LEFT, padx=2, fill=tk.X, expand=True)
                self.reading_vars[(direction, tariff)] = var

        # Рамка маршрутов (занимает всё оставшееся пространство)
        frame_table = tk.LabelFrame(self.root, text="Маршруты", padx=5, pady=5)
        frame_table.grid(row=3, column=0, sticky="nsew", padx=10, pady=5)

        self.canvas = tk.Canvas(frame_table, borderwidth=0, highlightthickness=0)
        self.scrollbar = tk.Scrollbar(frame_table, orient="vertical",
                                      command=self.canvas.yview)
        self.canvas.configure(yscrollcommand=self.scrollbar.set)
        self.canvas.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)

        self.routes_frame = tk.Frame(self.canvas)
        self.canvas.create_window((0, 0), window=self.routes_frame,
                                  anchor="nw", width=self.canvas.winfo_width())

        self.routes_frame.bind("<Configure>", self._on_frame_configure)
        self.canvas.bind("<Configure>", self._on_canvas_configure)

        self.create_table_header()

        # Статусная строка (всегда видна внизу)
        status_frame = tk.Frame(self.root, bg="#f0f0f0", height=25)
        status_frame.grid(row=4, column=0, sticky="ew", padx=0, pady=0)
        status_frame.grid_propagate(False)   # фиксируем высоту

        self.status_var = tk.StringVar(value="Готов")
        status_bar = tk.Label(status_frame, textvariable=self.status_var,
                              bd=1, relief=tk.SUNKEN, anchor=tk.W,
                              bg="#f0f0f0", font=("Arial", 9))
        status_bar.pack(side=tk.LEFT, fill=tk.X, expand=True)

        version_label = tk.Label(status_frame, text=f"Версия: {__version__}",
                                 bd=1, relief=tk.SUNKEN, anchor=tk.E,
                                 bg="#f0f0f0", font=("Arial", 9))
        version_label.pack(side=tk.RIGHT, padx=(5, 2))

    def create_table_header(self):
        header_frame = tk.Frame(self.routes_frame, bg="#d9d9d9", relief="flat", bd=1)
        header_frame.pack(fill=tk.X, pady=(0, 2))

        lbl_route_header = tk.Label(header_frame, text="Маршрут / IP",
                                    font=("Arial", 10, "bold"),
                                    bg="#d9d9d9", anchor="center")
        lbl_route_header.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=5, pady=3)

        sep_vert_header = ttk.Separator(header_frame, orient='vertical')
        sep_vert_header.pack(side=tk.LEFT, fill=tk.Y, padx=2, pady=2)

        right_header_frame = tk.Frame(header_frame, width=140, bg="#d9d9d9")
        right_header_frame.pack(side=tk.RIGHT, fill=tk.Y)
        right_header_frame.pack_propagate(False)

        lbl_status_header = tk.Label(right_header_frame, text="Статус пинга",
                                     font=("Arial", 10, "bold"),
                                     bg="#d9d9d9", anchor="center")
        lbl_status_header.pack(fill=tk.BOTH, expand=True, padx=5, pady=3)

        sep = ttk.Separator(self.routes_frame, orient='horizontal')
        sep.pack(fill=tk.X, pady=(0, 5))

    # ------------------------------------------------------------
    #  Управление Canvas
    # ------------------------------------------------------------
    def _on_frame_configure(self, event):
        self.canvas.configure(scrollregion=self.canvas.bbox("all"))

    def _on_canvas_configure(self, event):
        self.canvas.itemconfig(1, width=event.width)

    # ------------------------------------------------------------
    #  Авторизация и сохранение паролей
    # ------------------------------------------------------------
    def enable_paste(self, entry):
        def on_control_v(event):
            if event.keycode == 86 and (event.state & 0x4):
                entry.event_generate('<<Paste>>')
                return "break"
        entry.bind('<Key>', on_control_v)
        entry.bind('<Shift-Insert>', lambda e: entry.event_generate('<<Paste>>'))

    def save_credentials(self, login, password):
        with open(settings.CRED_FILE, 'wb') as f:
            pickle.dump({'login': login, 'password': password}, f)
        logger.debug("Учётные данные сохранены")

    def load_credentials(self):
        if os.path.exists(settings.CRED_FILE):
            try:
                with open(settings.CRED_FILE, 'rb') as f:
                    data = pickle.load(f)
                    return data.get('login'), data.get('password')
            except Exception as e:
                logger.error(f"Ошибка загрузки сохранённых данных: {e}")
        return None, None

    def do_login(self, login, password):
        logger.info(f"Попытка входа пользователя: {login}")
        self.status_var.set("Выполняется вход...")
        self.btn_get.config(state=tk.DISABLED)
        self.root.update()

        try:
            self.client.username = login
            self.client.password = password
            if self.client.login():
                self.current_user = login
                self.lbl_user.config(text=f"Пользователь: {login}")
                self.status_var.set("Авторизация успешна")
                logger.info(f"Пользователь {login} успешно авторизован")
                return True
            else:
                logger.warning(f"Неудачная авторизация для {login}")
                messagebox.showerror("Ошибка авторизации", "Неверный логин или пароль")
                self.status_var.set("Ошибка входа")
                return False
        except Exception as e:
            logger.exception(f"Исключение при авторизации: {e}")
            messagebox.showerror("Ошибка", f"Ошибка при входе:\n{str(e)}")
            self.status_var.set("Ошибка соединения")
            return False
        finally:
            self.btn_get.config(state=tk.NORMAL)

    def initial_login(self):
        login, password = self.load_credentials()
        if login and password:
            self.do_login(login, password)
        else:
            self.change_user()

    def change_user(self):
        dialog = tk.Toplevel(self.root)
        dialog.title("Смена пользователя")
        dialog.geometry("300x150")
        dialog.resizable(False, False)
        dialog.grab_set()

        tk.Label(dialog, text="Логин:").pack(pady=(10, 0))
        entry_login = tk.Entry(dialog, width=30)
        entry_login.pack(pady=5)

        tk.Label(dialog, text="Пароль:").pack()
        entry_password = tk.Entry(dialog, show="*", width=30)
        entry_password.pack(pady=5)

        self.enable_paste(entry_login)
        self.enable_paste(entry_password)

        def on_submit():
            login = entry_login.get().strip()
            password = entry_password.get().strip()
            if not login or not password:
                messagebox.showerror("Ошибка", "Логин и пароль не могут быть пустыми")
                return
            self.save_credentials(login, password)
            if self.do_login(login, password):
                dialog.destroy()

        btn_submit = tk.Button(dialog, text="Войти", command=on_submit,
                               bg="#4CAF50", fg="white")
        btn_submit.pack(pady=10)
        entry_password.bind("<Return>", lambda e: on_submit())
        entry_login.bind("<Return>", lambda e: on_submit())

        logger.debug("Открыто окно смены пользователя")

    # ------------------------------------------------------------
    #  Работа с данными прибора
    # ------------------------------------------------------------
    def extract_ip_from_route(self, route_str):
        match = re.search(r'\b(?:[0-9]{1,3}\.){3}[0-9]{1,3}\b', route_str)
        return match.group(0) if match else None

    def update_scrollbar_visibility(self):
        if len(self.route_rows) > 5:
            if not self.scrollbar.winfo_ismapped():
                self.scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
        else:
            if self.scrollbar.winfo_ismapped():
                self.scrollbar.pack_forget()

    def update_readings_panel(self, meter):
        logger.debug(f"Обновление панели показаний из Meter: {meter is not None}")
        for (direction, tariff), var in self.reading_vars.items():
            var.set("—")
        self.readings_frame.config(text="Показания, кВт·ч")

        if not meter:
            return

        if meter.meter_data_datetime:
            self.readings_frame.config(text=f"Показания, кВт·ч, {meter.meter_data_datetime}")

        mapping = {
            ("A+", "TO"): meter.t0plus,
            ("A+", "T1"): meter.t1plus,
            ("A+", "T2"): meter.t2plus,
            ("A-", "TO"): meter.t0minus,
            ("A-", "T1"): meter.t1minus,
            ("A-", "T2"): meter.t2minus,
        }
        for (direction, tariff), value in mapping.items():
            if value is not None:
                self.reading_vars[(direction, tariff)].set(str(value))

    def fetch_meter_data(self):
        if not self.client.access_token:
            messagebox.showerror("Ошибка",
                                 "Нет активной сессии. Пожалуйста, смените пользователя и войдите заново.")
            return

        meter_num = self.entry_meter_num.get().strip()
        if not meter_num:
            messagebox.showerror("Ошибка", "Введите номер прибора учета")
            return

        # Сброс
        self.current_instance_id = None
        self.current_meter = None
        self.btn_export.config(state=tk.DISABLED)
        self.btn_export_hourly.config(state=tk.DISABLED)

        logger.info(f"Запрос данных для прибора: {meter_num}")
        self.status_var.set("Поиск данных...")
        self.btn_get.config(state=tk.DISABLED)
        self.root.update()

        # Очистка маршрутов
        for row_frame, sep in self.route_rows:
            row_frame.destroy()
            if sep:
                sep.destroy()
        self.route_rows.clear()

        self.meter_model_var.set("—")
        self.address_var.set("—")
        self.account_var.set("—")
        self._full_address = ""
        self.lbl_address.config(text="—")
        self.update_readings_panel(None)

        try:
            meter = self.client.fetch_all_data(meter_num)
            if not meter:
                empty_frame = tk.Frame(self.routes_frame)
                empty_frame.pack(fill=tk.X, pady=5)
                tk.Label(empty_frame, text="Маршруты не найдены.",
                         fg="gray", anchor="center").pack(fill=tk.X, padx=5)
                self.route_rows.append((empty_frame, None))
                self.status_var.set("Маршруты не найдены")
                return

            self.current_meter = meter
            self.current_instance_id = meter.instance_id
            self.btn_export.config(state=tk.NORMAL)
            self.btn_export_hourly.config(state=tk.NORMAL)

            self.meter_model_var.set(meter.model)
            self.address_var.set(meter.address)
            self.account_var.set(meter.contract_num)
            self._full_address = meter.full_path
            self.lbl_address.config(text=meter.address)
            self.lbl_address.tooltip = meter.full_path

            self.update_readings_panel(meter)

            routes = meter.routes or []
            logger.info(f"Найдено маршрутов: {len(routes)}")
            for i, route in enumerate(routes):
                self.add_route_row(route, i % 2 == 0)
            self.status_var.set(f"Найдено маршрутов: {len(routes)}")
            self.update_scrollbar_visibility()

        except ValueError as e:
            logger.warning(f"Ошибка данных: {e}")
            messagebox.showerror("Ошибка", str(e))
            self.status_var.set("Ошибка данных")
        except Exception as e:
            logger.exception(f"Необработанная ошибка в fetch_meter_data: {e}")
            messagebox.showerror("Ошибка", f"Произошла ошибка:\n{str(e)}")
            self.status_var.set("Ошибка выполнения")
        finally:
            self.btn_get.config(state=tk.NORMAL)

    # ------------------------------------------------------------
    #  Маршруты и пинг
    # ------------------------------------------------------------
    def add_route_row(self, route_text, even=True):
        row_frame = tk.Frame(self.routes_frame)
        row_frame.pack(fill=tk.X, pady=(0, 0))
        bg_color = "#f9f9f9" if even else "#ffffff"
        row_frame.configure(bg=bg_color)

        entry_route = tk.Entry(row_frame, readonlybackground=bg_color,
                               borderwidth=0, highlightthickness=0,
                               font=("Arial", 9), justify="center")
        entry_route.insert(0, route_text)
        entry_route.configure(state='readonly')
        entry_route.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=(5, 0), pady=3)

        entry_route.bind('<Control-c>', lambda e: e.widget.event_generate('<<Copy>>'))
        entry_route.bind('<Control-C>', lambda e: e.widget.event_generate('<<Copy>>'))
        entry_route.bind('<Control-Insert>', lambda e: e.widget.event_generate('<<Copy>>'))

        vert_sep = ttk.Separator(row_frame, orient='vertical')
        vert_sep.pack(side=tk.LEFT, fill=tk.Y, padx=5, pady=3)

        right_frame = tk.Frame(row_frame, width=140, bg=bg_color)
        right_frame.pack(side=tk.RIGHT, fill=tk.Y)
        right_frame.pack_propagate(False)

        center_frame = tk.Frame(right_frame, bg=bg_color)
        center_frame.pack(expand=True)

        lbl_status = tk.Label(center_frame, text="", font=("Arial", 10), bg=bg_color)
        lbl_status.pack(side=tk.LEFT, padx=5)

        btn_retry = tk.Button(center_frame, text="Повторно", state=tk.DISABLED,
                              command=lambda: self.start_ping_for_row(route_text, lbl_status, btn_retry))
        btn_retry.pack(side=tk.LEFT)

        separator = ttk.Separator(self.routes_frame, orient='horizontal')
        separator.pack(fill=tk.X, pady=(0, 2))

        row_obj = type('Row', (), {
            'frame': row_frame,
            'ping_worker': None,
            'lbl_status': lbl_status,
            'btn_retry': btn_retry,
            'route_text': route_text
        })()
        self.route_rows.append((row_frame, separator))
        self.start_ping_for_row(route_text, lbl_status, btn_retry, row_obj)

    def start_ping_for_row(self, route_text, lbl_status, btn_retry, row_obj=None):
        ip = self.extract_ip_from_route(route_text)
        if not ip:
            lbl_status.config(text="❌ IP не найден", fg="red")
            btn_retry.config(state=tk.NORMAL)
            return

        if row_obj and row_obj.ping_worker:
            row_obj.ping_worker.stop()
            row_obj.ping_worker = None

        btn_retry.config(state=tk.DISABLED)
        lbl_status.config(text="пингуем...", fg="orange")

        def on_attempt(attempt, max_attempts):
            lbl_status.config(text=f"{attempt}/{max_attempts}", fg="orange")

        def on_finished(success):
            if success:
                lbl_status.config(text="✅", fg="green", font=("Arial", 12))
            else:
                lbl_status.config(text="❌", fg="red", font=("Arial", 12))
            btn_retry.config(state=tk.NORMAL)
            if row_obj:
                row_obj.ping_worker = None

        worker = PingWorker(ip, max_attempts=50,
                            attempt_callback=on_attempt,
                            finished_callback=on_finished)
        if row_obj:
            row_obj.ping_worker = worker
        worker.start()

    # ------------------------------------------------------------
    #  Выгрузка подневки
    # ------------------------------------------------------------
    def open_export_dialog(self):
        if not self.current_instance_id:
            messagebox.showerror("Ошибка", "Сначала получите данные прибора")
            return

        dialog = tk.Toplevel(self.root)
        dialog.title("Параметры выгрузки")
        dialog.geometry("480x10")
        dialog.resizable(False, False)
        dialog.grab_set()

        frame_dates = tk.Frame(dialog)
        frame_dates.pack(anchor='center', pady=(15, 5))

        tk.Label(frame_dates, text="Начало:").pack(side=tk.LEFT)
        entry_start = tk.Entry(frame_dates, width=12, justify='center')
        entry_start.pack(side=tk.LEFT, padx=(0, 30))
        entry_start.insert(0, date.today().strftime("%d.%m.%Y"))

        tk.Label(frame_dates, text="Конец:").pack(side=tk.LEFT)
        entry_finish = tk.Entry(frame_dates, width=12, justify='center')
        entry_finish.pack(side=tk.LEFT)
        entry_finish.insert(0, date.today().strftime("%d.%m.%Y"))

        frame_path = tk.Frame(dialog)
        frame_path.pack(anchor='center', fill=tk.X, padx=10, pady=(10, 5))
        btn_browse = tk.Button(frame_path, text="Обзор",
                               command=lambda: self._browse_folder(entry_dir))
        btn_browse.pack(side=tk.LEFT, padx=(0, 5))
        entry_dir = tk.Entry(frame_path)
        entry_dir.pack(side=tk.LEFT, fill=tk.X, expand=True)

        def on_submit():
            start_str = entry_start.get().strip()
            finish_str = entry_finish.get().strip()
            output_dir = entry_dir.get().strip()

            if not start_str or not finish_str or not output_dir:
                messagebox.showerror("Ошибка", "Заполните все поля")
                return

            try:
                start_date = datetime.strptime(start_str, "%d.%m.%Y")
                finish_date = datetime.strptime(finish_str, "%d.%m.%Y")
            except ValueError:
                messagebox.showerror("Ошибка", "Неверный формат даты. Используйте ДД.ММ.ГГГГ")
                return

            if not os.path.isdir(output_dir):
                messagebox.showerror("Ошибка", "Указанная папка не существует")
                return

            dialog.destroy()
            self.start_export(start_date, finish_date, output_dir)

        btn_ok = tk.Button(dialog, text="Выгрузить", command=on_submit,
                           bg="#4CAF50", fg="white", width=15)
        btn_ok.pack(pady=15)

        dialog.update_idletasks()
        req_h = dialog.winfo_reqheight()
        dialog.geometry(f"480x{req_h}")

    def _browse_folder(self, entry_widget):
        folder_selected = filedialog.askdirectory()
        if folder_selected:
            entry_widget.delete(0, tk.END)
            entry_widget.insert(0, folder_selected)

    def start_export(self, start_date, finish_date, output_path):
        progress_win = tk.Toplevel(self.root)
        progress_win.title("Выгрузка...")
        progress_win.geometry("300x100")
        progress_win.resizable(False, False)
        progress_win.grab_set()
        progress_win.transient(self.root)

        tk.Label(progress_win, text="Идёт формирование отчёта, подождите...").pack(pady=(15, 5))
        progress_bar = ttk.Progressbar(progress_win, mode='indeterminate')
        progress_bar.pack(pady=10, padx=30, fill=tk.X)
        progress_bar.start()

        def run_export():
            try:
                saved_path = self.client.create_meter_daily_data_report(
                    instance_id=self.current_instance_id,
                    start_date=start_date,
                    finish_date=finish_date,
                    output_path=output_path
                )
                self.root.after(0, _on_export_success, saved_path)
            except Exception as e:
                self.root.after(0, _on_export_error, str(e))

        def _on_export_success(path):
            progress_bar.stop()
            progress_win.destroy()
            messagebox.showinfo("Готово", f"Отчёт сохранён:\n{path}")

        def _on_export_error(error_msg):
            progress_bar.stop()
            progress_win.destroy()
            messagebox.showerror("Ошибка выгрузки", f"Не удалось выполнить выгрузку:\n{error_msg}")

        threading.Thread(target=run_export, daemon=True).start()

    # ------------------------------------------------------------
    #  Выгрузка почасовки (новое окно с датами)
    # ------------------------------------------------------------
    def open_export_hourly_dialog(self):
        if not self.current_meter:
            messagebox.showerror("Ошибка", "Сначала получите данные прибора")
            return

        dialog = tk.Toplevel(self.root)
        dialog.title("Параметры выгрузки почасовки")
        dialog.geometry("480x10")
        dialog.resizable(False, False)
        dialog.grab_set()

        frame_dates = tk.Frame(dialog)
        frame_dates.pack(anchor='center', pady=(15, 5))

        tk.Label(frame_dates, text="Начало:").pack(side=tk.LEFT)
        entry_start = tk.Entry(frame_dates, width=12, justify='center')
        entry_start.pack(side=tk.LEFT, padx=(0, 30))
        entry_start.insert(0, date.today().strftime("%d.%m.%Y"))

        tk.Label(frame_dates, text="Конец:").pack(side=tk.LEFT)
        entry_finish = tk.Entry(frame_dates, width=12, justify='center')
        entry_finish.pack(side=tk.LEFT)
        entry_finish.insert(0, date.today().strftime("%d.%m.%Y"))

        frame_path = tk.Frame(dialog)
        frame_path.pack(anchor='center', fill=tk.X, padx=10, pady=(10, 5))
        btn_browse = tk.Button(frame_path, text="Обзор",
                               command=lambda: self._browse_folder(entry_dir))
        btn_browse.pack(side=tk.LEFT, padx=(0, 5))
        entry_dir = tk.Entry(frame_path)
        entry_dir.pack(side=tk.LEFT, fill=tk.X, expand=True)

        def on_submit():
            start_str = entry_start.get().strip()
            finish_str = entry_finish.get().strip()
            output_dir = entry_dir.get().strip()

            if not start_str or not finish_str or not output_dir:
                messagebox.showerror("Ошибка", "Заполните все поля")
                return

            try:
                start_date = datetime.strptime(start_str, "%d.%m.%Y")
                finish_date = datetime.strptime(finish_str, "%d.%m.%Y")
            except ValueError:
                messagebox.showerror("Ошибка", "Неверный формат даты. Используйте ДД.ММ.ГГГГ")
                return

            if not os.path.isdir(output_dir):
                messagebox.showerror("Ошибка", "Указанная папка не существует")
                return

            dialog.destroy()
            self.start_hourly_export(start_date, finish_date, output_dir)

        btn_ok = tk.Button(dialog, text="Выгрузить", command=on_submit,
                           bg="#4CAF50", fg="white", width=15)
        btn_ok.pack(pady=15)

        dialog.update_idletasks()
        req_h = dialog.winfo_reqheight()
        dialog.geometry(f"480x{req_h}")

    def start_hourly_export(self, start_dt, end_dt, output_path):
        progress_win = tk.Toplevel(self.root)
        progress_win.title("Выгрузка почасовки...")
        progress_win.geometry("300x100")
        progress_win.resizable(False, False)
        progress_win.grab_set()
        progress_win.transient(self.root)

        tk.Label(progress_win, text="Идёт формирование отчёта, подождите...").pack(pady=(15, 5))
        progress_bar = ttk.Progressbar(progress_win, mode='indeterminate')
        progress_bar.pack(pady=10, padx=30, fill=tk.X)
        progress_bar.start()

        def run_export():
            try:
                saved_path = self.client.create_file_report_async(
                    start_dt=start_dt,
                    end_dt=end_dt,
                    output_path=output_path,
                    meter=self.current_meter
                )
                self.root.after(0, _on_export_success, saved_path)
            except Exception as e:
                self.root.after(0, _on_export_error, str(e))

        def _on_export_success(path):
            progress_bar.stop()
            progress_win.destroy()
            messagebox.showinfo("Готово", f"Отчёт сохранён:\n{path}")

        def _on_export_error(error_msg):
            progress_bar.stop()
            progress_win.destroy()
            messagebox.showerror("Ошибка выгрузки", f"Не удалось выполнить выгрузку:\n{error_msg}")

        threading.Thread(target=run_export, daemon=True).start()

    # ------------------------------------------------------------
    #  Обновление программы
    # ------------------------------------------------------------
    def check_for_updates(self):
        logger.info("Проверка наличия обновлений...")
        threading.Thread(target=self._check_update_thread, daemon=True).start()

    def _check_update_thread(self):
        try:
            update_info = updater.check_update()
            if update_info:
                logger.info("Найдено обновление")
                self.root.after(0, self.show_update_dialog, update_info)
            else:
                logger.info("Нет доступных обновлений")
        except Exception as e:
            logger.error(f"Ошибка при проверке обновлений: {e}")

    def show_update_dialog(self, update_info):
        new_version = update_info["version"]
        changelog = update_info["changelog"]
        url = update_info["url"]

        title = f"Доступна новая версия: {new_version}"
        message = f"Вышла новая версия {new_version}!\n\nЧто нового:\n{changelog}\n\nЖелаете обновиться?"

        if messagebox.askyesno(title, message):
            self.start_update(url)

    def start_update(self, url, new_version=""):
        progress_win = tk.Toplevel(self.root)
        ver_str = f"Обновление до версии {new_version}" if new_version else "Обновление"
        progress_win.title(ver_str)
        win_w, win_h = 360, 180
        progress_win.geometry(f"{win_w}x{win_h}")
        progress_win.resizable(False, False)
        progress_win.grab_set()
        progress_win.transient(self.root)

        self.root.update_idletasks()
        main_x = self.root.winfo_x()
        main_y = self.root.winfo_y()
        main_w = self.root.winfo_width()
        main_h = self.root.winfo_height()
        x = main_x + (main_w - win_w) // 2
        y = main_y + (main_h - win_h) // 2
        progress_win.geometry(f"{win_w}x{win_h}+{x}+{y}")

        status_font = ("Arial", 8)
        wrap_length = win_w - 40

        frame_status = tk.Frame(progress_win)
        lbl_conn = tk.Label(frame_status, text="Подключение...", font=status_font,
                            wraplength=wrap_length, justify="center")
        lbl_conn.pack(pady=(5, 0))
        lbl_attempt = tk.Label(frame_status, text="", font=status_font,
                               wraplength=wrap_length, justify="center")
        lbl_attempt.pack(pady=(2, 5))

        frame_progress = tk.Frame(progress_win)
        progress_var = tk.DoubleVar()
        progress_bar = ttk.Progressbar(frame_progress, variable=progress_var,
                                       maximum=100, mode='determinate', length=300)
        lbl_size = tk.Label(frame_progress, text="", font=status_font, justify="center")

        progress_bar.pack(pady=(0, 5))
        lbl_size.pack(pady=(0, 10))

        progress_win.update_idletasks()
        frame_status.place(relx=0.5, rely=0.5, anchor='center')

        def show_progress_widgets():
            frame_status.place_forget()
            frame_progress.place(relx=0.5, rely=0.5, anchor='center')

        def status_update(message, attempt):
            if attempt == 0:
                lbl_conn.config(text="Соединение установлено. Загрузка...")
                lbl_attempt.config(text="")
                progress_win.after(300, show_progress_widgets)
            else:
                lbl_conn.config(text=message)
                lbl_attempt.config(text=f"Попытка {attempt}")

        def update_progress(percent, downloaded_bytes, total_bytes):
            progress_var.set(percent)
            def fmt(b):
                for unit in ['Б', 'КБ', 'МБ', 'ГБ']:
                    if b < 1024:
                        return f"{b:.1f} {unit}" if unit != 'Б' else f"{int(b)} {unit}"
                    b /= 1024
                return f"{b:.1f} ТБ"
            size_text = f"Скачано: {fmt(downloaded_bytes)} / {fmt(total_bytes)}"
            lbl_size.config(text=size_text)

        def on_download_finished(filepath):
            progress_win.destroy()
            if filepath:
                try:
                    subprocess.Popen([filepath])
                except Exception as e:
                    messagebox.showerror("Ошибка", f"Не удалось запустить установщик:\n{e}")
            self.root.quit()
            self.root.destroy()

        def run_download():
            try:
                filepath = updater.download_and_install(
                    progress_callback=lambda p, d, t: self.root.after(0, update_progress, p, d, t),
                    status_callback=lambda msg, attempt: self.root.after(0, status_update, msg, attempt)
                )
                self.root.after(0, on_download_finished, filepath)
            except Exception as e:
                logger.error(f"Ошибка загрузки обновления: {e}")
                self.root.after(0, progress_win.destroy)
                self.root.after(0, messagebox.showerror, "Ошибка", f"Не удалось загрузить обновление:\n{e}")

        threading.Thread(target=run_download, daemon=True).start()


app = PyramidApp()
