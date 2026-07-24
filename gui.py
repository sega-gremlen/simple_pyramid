import tkinter as tk
from tkinter import ttk, messagebox, filedialog
from tkinter import PhotoImage
import pickle
import os
import re
import logging
import threading
from datetime import datetime, date

from backend import PyramidApiClient
from utils.pinger import PingWorker
import updater
from version import __version__

# Настройка логирования
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    datefmt='%H:%M:%S'
)
logger = logging.getLogger(__name__)

CRED_FILE = "pyramid_creds.pkl"


class PyramidApp:
    def __init__(self):
        self.root = tk.Tk()
        # self.root.iconbitmap('./src/favicon.ico')
        self.root.title("Простая Пирамида")
        self.root.geometry("850x620")
        self.root.resizable(False, False)

        self.client = PyramidApiClient()
        self.current_user = None
        self.current_instance_id = None
        self.route_rows = []

        self.create_widgets()
        self.root.after(100, self.initial_login)
        self.root.after(500, self.check_for_updates)  # Проверка обновлений
        logger.info("Приложение запущено")
        
    def start(self):
        self.root.mainloop()
        

    def create_widgets(self):
        # Верхняя панель
        top_frame = tk.Frame(self.root)
        top_frame.pack(fill=tk.X, padx=10, pady=5)

        self.lbl_user = tk.Label(top_frame, text="Пользователь: не авторизован", anchor=tk.W, font=("Arial", 9))
        self.lbl_user.pack(side=tk.LEFT, fill=tk.X, expand=True)

        btn_change_user = tk.Button(top_frame, text="Сменить пользователя", command=self.change_user, bg="#FF9800")
        btn_change_user.pack(side=tk.RIGHT)

        # Рамка параметров поиска (теперь в одну строку)
        frame_meter = tk.LabelFrame(self.root, text="Параметры поиска", padx=10, pady=5)
        frame_meter.pack(fill="x", padx=10, pady=5)
        
        # Размещаем в одной строке: метка, поле ввода, кнопка
        tk.Label(frame_meter, text="Номер прибора учета (ПУ):").grid(row=0, column=0, sticky="w", padx=(0, 10))
        self.entry_meter_num = tk.Entry(frame_meter, width=30)
        self.enable_paste(self.entry_meter_num)
        self.entry_meter_num.grid(row=0, column=1, padx=(0, 10))
        self.entry_meter_num.bind("<Return>", lambda e: self.fetch_meter_data())

        self.btn_get = tk.Button(frame_meter, text="Получить данные", command=self.fetch_meter_data,
                                 bg="#4CAF50", fg="white", font=("Arial", 10, "bold"))
        self.btn_get.grid(row=0, column=2)
        
        #Кнопка выгрузки (изначально недоступна)
        self.btn_export = tk.Button(frame_meter, text="Сделать выгрузку", command=self.open_export_dialog,
                                    bg="#2196F3", fg="white", font=("Arial", 10, "bold"),
                                    state=tk.DISABLED)
        self.btn_export.grid(row=0, column=3, padx=(10, 0))

        # Горизонтальная панель: информация о приборе и показания
        main_info_row = tk.Frame(self.root)
        main_info_row.pack(fill="x", padx=10, pady=5)

        # Левая панель
        self.info_frame = tk.LabelFrame(main_info_row, text="Информация о точке", padx=10, pady=10)
        self.info_frame.pack(side=tk.LEFT, fill="both", expand=True, padx=(0, 5))

        self.meter_model_var = tk.StringVar(value="—")
        self.address_var = tk.StringVar(value="—")
        self.account_var = tk.StringVar(value="—")

        tk.Label(self.info_frame, text="Тип счетчика:", font=("Arial", 9, "bold")).grid(row=0, column=0, sticky="w", pady=2)
        tk.Label(self.info_frame, textvariable=self.meter_model_var, font=("Arial", 9)).grid(row=0, column=1, sticky="w", padx=(10, 0), pady=2)

        tk.Label(self.info_frame, text="Место установки:", font=("Arial", 9, "bold")).grid(row=1, column=0, sticky="w", pady=2)
        lbl_address = tk.Label(self.info_frame, textvariable=self.address_var, font=("Arial", 9), anchor="w")
        lbl_address.grid(row=1, column=1, sticky="w", padx=(10, 0), pady=2)
        self.lbl_address = lbl_address
        self._full_address = ""

        tk.Label(self.info_frame, text="Лицевой счет:", font=("Arial", 9, "bold")).grid(row=2, column=0, sticky="w", pady=2)
        tk.Label(self.info_frame, textvariable=self.account_var, font=("Arial", 9)).grid(row=2, column=1, sticky="w", padx=(10, 0), pady=2)

        # Правая панель — показания (фиксированная ширина)
        self.readings_frame = tk.LabelFrame(main_info_row, text="Показания, кВт·ч", padx=10, pady=10, width=280)
        self.readings_frame.pack(side=tk.RIGHT, fill="both", padx=(5, 0))

        header_row = tk.Frame(self.readings_frame)
        header_row.pack(fill=tk.X, pady=(0, 5))
        tk.Label(header_row, text="", width=6).pack(side=tk.LEFT)
        self.lbl_a_plus = tk.Label(header_row, text="A+", font=("Arial", 9, "bold"), anchor="center")
        self.lbl_a_plus.pack(side=tk.LEFT, padx=2, fill=tk.X, expand=True)
        self.lbl_a_minus = tk.Label(header_row, text="A−", font=("Arial", 9, "bold"), anchor="center")
        self.lbl_a_minus.pack(side=tk.LEFT, padx=2, fill=tk.X, expand=True)

        self.reading_vars = {}
        for tariff in ["TO", "T1", "T2"]:
            row_frame = tk.Frame(self.readings_frame)
            row_frame.pack(fill=tk.X, pady=2)
            tk.Label(row_frame, text=tariff, font=("Arial", 9), width=3, anchor="e").pack(side=tk.LEFT, padx=(0, 2))
            for direction in ["A+", "A-"]:
                var = tk.StringVar(value="—")
                lbl = tk.Label(row_frame, textvariable=var, font=("Arial", 9), width=12, anchor="center",
                               relief=tk.SUNKEN, bd=1)
                lbl.pack(side=tk.LEFT, padx=2, fill=tk.X, expand=True)
                self.reading_vars[(direction, tariff)] = var

        # Рамка для маршрутов
        frame_table = tk.LabelFrame(self.root, text="Маршруты", padx=5, pady=5)
        frame_table.pack(fill="both", expand=True, padx=10, pady=5)

        self.canvas = tk.Canvas(frame_table, borderwidth=0, highlightthickness=0)
        self.scrollbar = tk.Scrollbar(frame_table, orient="vertical", command=self.canvas.yview)
        self.canvas.configure(yscrollcommand=self.scrollbar.set)
        self.canvas.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)

        self.routes_frame = tk.Frame(self.canvas)
        self.canvas.create_window((0, 0), window=self.routes_frame, anchor="nw", width=self.canvas.winfo_width())

        self.routes_frame.bind("<Configure>", self._on_frame_configure)
        self.canvas.bind("<Configure>", self._on_canvas_configure)

        self.create_table_header()

        # Статусная строка (внизу) с цветным фоном и версией
        status_frame = tk.Frame(self.root, bg="#f0f0f0")
        status_frame.pack(side=tk.BOTTOM, fill=tk.X)

        self.status_var = tk.StringVar(value="Готов")
        status_bar = tk.Label(status_frame, textvariable=self.status_var, bd=1, relief=tk.SUNKEN, anchor=tk.W,
                              bg="#f0f0f0", font=("Arial", 9))
        status_bar.pack(side=tk.LEFT, fill=tk.X, expand=True)

        version_label = tk.Label(status_frame, text=f"Версия: {__version__}", bd=1, relief=tk.SUNKEN, anchor=tk.E,
                                 bg="#f0f0f0", font=("Arial", 9))
        version_label.pack(side=tk.RIGHT, padx=(5, 2))

    def create_table_header(self):
        """Заголовки таблицы маршрутов"""
        header_frame = tk.Frame(self.routes_frame, bg="#d9d9d9", relief="flat", bd=1)
        header_frame.pack(fill=tk.X, pady=(0, 2))

        lbl_route_header = tk.Label(header_frame, text="Маршрут / IP", font=("Arial", 10, "bold"),
                                    bg="#d9d9d9", anchor="center")
        lbl_route_header.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=5, pady=3)

        sep_vert_header = ttk.Separator(header_frame, orient='vertical')
        sep_vert_header.pack(side=tk.LEFT, fill=tk.Y, padx=2, pady=2)

        right_header_frame = tk.Frame(header_frame, width=140, bg="#d9d9d9")
        right_header_frame.pack(side=tk.RIGHT, fill=tk.Y)
        right_header_frame.pack_propagate(False)

        lbl_status_header = tk.Label(right_header_frame, text="Статус пинга", font=("Arial", 10, "bold"),
                                     bg="#d9d9d9", anchor="center")
        lbl_status_header.pack(fill=tk.BOTH, expand=True, padx=5, pady=3)

        sep = ttk.Separator(self.routes_frame, orient='horizontal')
        sep.pack(fill=tk.X, pady=(0, 5))

    def _on_frame_configure(self, event):
        self.canvas.configure(scrollregion=self.canvas.bbox("all"))

    def _on_canvas_configure(self, event):
        self.canvas.itemconfig(1, width=event.width)

    def enable_paste(self, entry):
        def on_control_v(event):
            if event.keycode == 86 and (event.state & 0x4):
                entry.event_generate('<<Paste>>')
                return "break"
        entry.bind('<Key>', on_control_v)
        entry.bind('<Shift-Insert>', lambda e: entry.event_generate('<<Paste>>'))

    def save_credentials(self, login, password):
        with open(CRED_FILE, 'wb') as f:
            pickle.dump({'login': login, 'password': password}, f)
        logger.debug("Учётные данные сохранены")

    def load_credentials(self):
        if os.path.exists(CRED_FILE):
            try:
                with open(CRED_FILE, 'rb') as f:
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

        btn_submit = tk.Button(dialog, text="Войти", command=on_submit, bg="#4CAF50", fg="white")
        btn_submit.pack(pady=10)
        entry_password.bind("<Return>", lambda e: on_submit())
        entry_login.bind("<Return>", lambda e: on_submit())

        logger.debug("Открыто окно смены пользователя")

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

    def update_readings_panel(self, reading_data):
        """Обновляет панель показаний. Дата добавляется в заголовок."""
        logger.debug(f"Обновление панели показаний: {reading_data is not None}")
        for (direction, tariff), var in self.reading_vars.items():
            var.set("—")
        self.readings_frame.config(text="Показания, кВт·ч")

        if not reading_data or not isinstance(reading_data, dict):
            return

        if "register_datetime" in reading_data:
            dt = reading_data["register_datetime"]
            self.readings_frame.config(text=f"Показания, кВт·ч, {dt}")
            logger.info(f"Дата показаний: {dt}")

        fine_values = reading_data.get("fine_meter_values")
        if not isinstance(fine_values, dict):
            logger.warning("Нет fine_meter_values в данных")
            return

        for direction in ["A+", "A-"]:
            dir_data = fine_values.get(direction)
            if not isinstance(dir_data, dict):
                continue
            for tariff in ["TO", "T1", "T2"]:
                value = dir_data.get(tariff)
                if value is not None:
                    formatted = str(value)
                    self.reading_vars[(direction, tariff)].set(formatted)
                    logger.debug(f"Установлено {direction}/{tariff} = {formatted}")

    def fetch_meter_data(self):
        if not self.client.access_token:
            logger.error("Попытка запроса без активной сессии")
            messagebox.showerror("Ошибка", "Нет активной сессии. Пожалуйста, смените пользователя и войдите заново.")
            return

        meter_num = self.entry_meter_num.get().strip()
        if not meter_num:
            messagebox.showerror("Ошибка", "Введите номер прибора учета")
            return
        
        self.current_instance_id = None
        self.btn_export.config(state=tk.DISABLED)

        logger.info(f"Запрос данных для прибора: {meter_num}")
        self.status_var.set("Поиск данных...")
        self.btn_get.config(state=tk.DISABLED)
        self.root.update()

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
            response = self.client.get_meter_instance_data(meter_num)
            if not response:
                logger.warning(f"Нет данных о приборе {meter_num}")
                empty_frame = tk.Frame(self.routes_frame)
                empty_frame.pack(fill=tk.X, pady=5)
                empty_label = tk.Label(empty_frame, text="Маршруты не найдены.", fg="gray", anchor="center")
                empty_label.pack(fill=tk.X, padx=5)
                self.route_rows.append((empty_frame, None))
                self.status_var.set("Маршруты не найдены")
            else:
                if "meter_model" in response:
                    self.meter_model_var.set(response["meter_model"])
                    logger.debug(f"Модель счетчика: {response['meter_model']}")

                instance_id = response.get("instance_id") or meter_num
                self.current_instance_id = instance_id
                self.btn_export.config(state=tk.NORMAL)
                logger.debug(f"instance_id = {instance_id}")

                try:
                    rd_data = self.client.get_rd_instance_data(instance_id)
                    if rd_data:
                        if rd_data.get("address"):
                            raw_addr = rd_data["address"]
                            self._full_address = raw_addr
                            if len(raw_addr) > 71:
                                display_addr = "..." + raw_addr[len(raw_addr) - 68:len(raw_addr)]
                            else:
                                display_addr = raw_addr
                            self.address_var.set(display_addr)
                            self.lbl_address.config(text=display_addr)
                            self.lbl_address.tooltip = raw_addr
                            logger.debug(f"Адрес: {raw_addr} (отображается: {display_addr})")
                        if rd_data.get("account_id"):
                            self.account_var.set(rd_data["account_id"])
                            logger.debug(f"Лицевой счет: {rd_data['account_id']}")
                except Exception as e:
                    logger.error(f"Ошибка получения данных точки учета: {e}")

                try:
                    reading_data = self.client.get_meter_data(instance_id)
                    self.update_readings_panel(reading_data)
                    logger.info("Показания успешно получены")
                except Exception as e:
                    logger.error(f"Ошибка получения показаний: {e}")

                routes = response.get("meter_routes", [])
                logger.info(f"Найдено маршрутов: {len(routes)}")
                for i, route in enumerate(routes):
                    self.add_route_row(route, i % 2 == 0)
                self.status_var.set(f"Найдено маршрутов: {len(routes)}")

            self.update_scrollbar_visibility()
        except Exception as e:
            logger.exception(f"Необработанная ошибка в fetch_meter_data: {e}")
            messagebox.showerror("Ошибка", f"Произошла ошибка:\n{str(e)}")
            self.status_var.set("Ошибка выполнения")
        finally:
            self.btn_get.config(state=tk.NORMAL)

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
            logger.debug(f"IP не найден в строке: {route_text}")
            lbl_status.config(text="❌ IP не найден", fg="red")
            btn_retry.config(state=tk.NORMAL)
            return

        logger.debug(f"Запуск пинга для IP {ip} (маршрут: {route_text[:50]}...)")
        if row_obj and row_obj.ping_worker:
            row_obj.ping_worker.stop()
            row_obj.ping_worker = None

        btn_retry.config(state=tk.DISABLED)
        lbl_status.config(text="пингуем...", fg="orange")

        def on_attempt(attempt, max_attempts):
            lbl_status.config(text=f"попытка {attempt}/{max_attempts}", fg="orange")

        def on_finished(success):
            if success:
                lbl_status.config(text="✅", fg="green", font=("Arial", 12))
                logger.info(f"Пинг успешен для {ip}")
            else:
                lbl_status.config(text="❌", fg="red", font=("Arial", 12))
                logger.warning(f"Пинг не удался для {ip} после всех попыток")
            btn_retry.config(state=tk.NORMAL)
            if row_obj:
                row_obj.ping_worker = None

        worker = PingWorker(ip, max_attempts=50,
                            attempt_callback=on_attempt,
                            finished_callback=on_finished)
        if row_obj:
            row_obj.ping_worker = worker
        worker.start()

    def open_export_dialog(self):
        if not self.current_instance_id:
            messagebox.showerror("Ошибка", "Сначала получите данные прибора")
            return

        dialog = tk.Toplevel(self.root)
        dialog.title("Параметры выгрузки")
        dialog.geometry("350x250")
        dialog.resizable(False, False)
        dialog.grab_set()

        tk.Label(dialog, text="Начальная дата (ДД.ММ.ГГГГ):").pack(pady=(15, 0))
        entry_start = tk.Entry(dialog, width=20)
        entry_start.pack(pady=5)
        entry_start.insert(0, date.today().strftime("%d.%m.%Y"))

        tk.Label(dialog, text="Конечная дата (ДД.ММ.ГГГГ):").pack(pady=(5, 0))
        entry_finish = tk.Entry(dialog, width=20)
        entry_finish.pack(pady=5)
        entry_finish.insert(0, date.today().strftime("%d.%m.%Y"))

        tk.Label(dialog, text="Папка для сохранения:").pack(pady=(10, 0))
        frame_dir = tk.Frame(dialog)
        frame_dir.pack(pady=5)
        entry_dir = tk.Entry(frame_dir, width=25)
        entry_dir.pack(side=tk.LEFT)
        btn_browse = tk.Button(frame_dir, text="Обзор", command=lambda: self._browse_folder(entry_dir))
        btn_browse.pack(side=tk.LEFT, padx=5)

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

        btn_ok = tk.Button(dialog, text="Выгрузить", command=on_submit, bg="#4CAF50", fg="white", width=15)
        btn_ok.pack(pady=15)

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
            logger.info(f"Выгрузка завершена")

        def _on_export_error(error_msg):
            progress_bar.stop()
            progress_win.destroy()
            messagebox.showerror("Ошибка выгрузки", f"Не удалось выполнить выгрузку:\n{error_msg}")
            logger.error(f"Ошибка выгрузки: {error_msg}")

        threading.Thread(target=run_export, daemon=True).start()

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

    def start_update(self, url):

        def run_download():
            try:
                #updater.download_and_install(url, lambda p: self.root.after(0, update_progress, p))
                updater.download_via_curl(url)
                #updater.download_and_install_v2(url, lambda p: self.root.after(0, update_progress, p))
            except Exception as e:
                logger.error(f"Ошибка загрузки обновления: {e}")

        threading.Thread(target=run_download, daemon=True).start()

if __name__ == "__main__":
    app = PyramidApp()
    app.start()