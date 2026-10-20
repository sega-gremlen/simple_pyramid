# Простая Пирамида

Десктоп-программа для инженеров Сызранского РЭС: по номеру прибора учёта (ПУ) быстро показывает
данные из корпоративного ПО «Пирамида» — тип счётчика, адрес, договор, показания A+/A− по зонам,
состояние реле и лимит, журнал событий, маршруты связи с пингом; выгружает подневку и почасовку в xlsx.

@agents.md

## Стек

- Python 3.13, **uv** (`pyproject.toml` + `uv.lock`), пакет в `src/simple_pyramid`.
- UI: **pywebview** (Edge WebView2) + обычные HTML/CSS/JS без фреймворков и сборщиков.
- HTTP: **httpx.AsyncClient**; модели: **Pydantic v2**; настройки: **pydantic-settings**.
- Сборка: PyInstaller (`simple_pyramid.spec`) → Inno Setup (`installer/setup.iss`).
- Пароль хранится в Windows Credential Manager (`keyring`).

## Команды

```bash
uv sync                                   # зависимости (dev-группа ставится по умолчанию)
uv run python -m simple_pyramid           # запуск против боевого сервера (только с рабочего ПК)
uv run python -m dev.run [--fast]         # приложение + эмулятор Пирамиды (дома)
uv run python -m dev.web_preview          # тот же UI в браузере: http://127.0.0.1:8770
uv run python -m dev.ui_check [шаги...]   # автопрогон сценария в окне + снимки DOM
uv run python -m dev.mock_server          # только эмулятор на :8765

uv run ruff check . && uv run ruff format --check . && uv run mypy && uv run pytest --cov
uv run pyinstaller simple_pyramid.spec --noconfirm    # → dist/simple_pyramid/
uv run pre-commit install                 # один раз: проверки перед коммитом
```

На Windows для вывода кириллицы в pytest: `PYTHONIOENCODING=utf-8`.

## Архитектура

```
src/simple_pyramid/
  __main__.py         точка входа
  config.py           Settings (env PYRAMID_*, .env): api_url, таймауты, mock, debug
  version.py          __version__ = "0.0.0.dev0" в репо; реальную пишет CI. Руками НЕ менять
  api/                всё про HTTP-API Пирамиды
    client.py         PyramidClient: логин, авто-перелогин при 401 (один на все параллельные запросы)
    endpoints.py      пути эндпоинтов
    tasks.py          wait_for_task — общий поллер фоновых задач (лог задачи → UI)
    errors.py         PyramidError и наследники; str(exc) показывается пользователю
    models/           Pydantic-модели запросов и ответов
  domain/             чистая логика без I/O (легко тестировать)
    readings.py       выбор актуальных показаний TO/T1/T2 (см. docstring)
    meter.py, load.py, events.py, daily.py, period.py, models.py (DTO для фронта)
  services/
    meter_service.py  сценарии: find → load_details (параллельно, потоково), refresh_*, выгрузки
    sink.py           Sink-протокол «бэкенд → UI», Section, StatusKind
    xlsx_export.py    xlsx подневки (формат как в старых версиях — проверяется тестом)
  desktop/            всё, что знает про pywebview/Windows
    bridge.py         Api — методы, которые вызывает JS (pywebview.api.*)
    window.py         создание окна, адаптер WindowControl
    runner.py         asyncio-loop в фоновом потоке
    emitter.py        emit(event, payload) → window.on<Event>(payload) в JS
    pinger.py, updater.py, credentials.py
  ui/                 index.html (главное окно), daily.html, events.html (отдельные окна);
                      css/{tokens,components,app,child}.css;
                      js/core.js (помощники, подсказки, статус-строка, даты, ошибки), app.js (главное),
                      child.js (общее для доп. окон), daily.js, events.js
dev/                  эмулятор и инструменты разработчика (в сборку не попадают)
tests/unit, tests/integration, tests/data
installer/            setup.iss, favicon.ico, установщик WebView2
```

### Поток данных
JS → `pywebview.api.search(num)` → `Api._spawn(...)` ставит корутину в `AsyncRunner` → `MeterService`
шлёт события через `Sink.emit` → `WindowEmitter` → `window.onMeterPart({section, data, error})` и т.п.
Долгие операции не блокируют JS; короткие запрос-ответ (страница событий, подневка) возвращают значение.

События в JS: `Status{text,kind}`, `Error{title,message,details}`, `Auth`, `SearchStarted`, `SearchFailed`,
`MeterPart{section,data,error}`, `SectionBusy{section,busy}`, `TaskLog{section,text}`, `Ping`, `Export`,
`Update`, `WhatsNew`, `UpdateStatus`, `UpdateProgress`.
Методы моста: `bootstrap, login, logout, search, ping, refresh(section), cancel(section), events_page,
validate_period, daily_view, export, export_here, browse_folder, open_folder, open_daily, open_events,
window_context, fit_height, start_update, close`.
События рассылаются во **все** открытые окна (`WindowEmitter`), каждая страница обрабатывает своё.
Выгрузка несёт `source` (`main`/`daily`) — прогресс показывает только окно-источник.

### Интерфейс
- Главное окно 607 px (минимальная ширина). Без шапки: логин в заголовке окна, справа на панели —
  квадратные иконки: События (круг с «!», счётчик важных), Подневка (календарь), Почасовка (часы), Выход.
- Названия разделов врезаны в верхнюю рамку карточки (`.card-label`), справа в рамке — время данных (`.card-meta`).
- «Точка учёта» — три строки (тип + алярм-иконка, договор, адрес), между подписью и значением — точки.
- Ниже «Показания» (все числа по центру) и «Нагрузка» (реле с точкой, лимит в кВт).
- ↻ в углу «Показаний» и «Нагрузки» — опрос прибора; во время опроса — ✕ «отменить», блок мерцает.
- «События» и «Подневка» — **отдельные окна** программы (`desktop/window.py: CHILD_WINDOWS`), не меняют
  главное. События — по 10 при прокрутке, «Только важные», квадратная ↻ «Обновить данные».
  Подневка — пресеты (месяц, прошлый, 3/6/9 месяцев, год), «Скачать xlsx» рядом с «Показать».
- Высота главного окна = низ последнего маршрута + статус-строка (`fitWindowHeight`).
- Цветовая схема — **C «Синие панели»** (выбрана по макетам `dev/design/palettes.html`): тёмно-синяя
  панель поиска (`--bar-*`) и статус-строка (`--status-*`), между ними светлый контент; подсказки —
  того же тёмно-синего (`--tip-*`), а не чёрные. Тип сообщения в статус-строке — цветной кружок со значком.
  Доп. окна в том же стиле: панель опций (`.tools`) и нижняя полоса (`.strip`) синие, таблица белая;
  цветной текст на синем — `--on-bar-*`.
- Один шрифт (`--sans`) везде, числа табличные, разряды — узкий пробел (`fmtNumber`).
- Подсказки — одна система на JS (`data-tip`, рисует core.js) для кнопок, значений и иконок; `title` не использовать.
- Статус-строка: появляется и гаснет (`STATUS_*` в core.js), клик — история; ошибки — модальное окно.
- Пустое состояние до первого поиска — серая картинка и серое «Найдите прибор учёта» ровно по центру;
  подсказка эмулятора прижата к низу и центровку не сдвигает; нет значения — `naHtml()` («нет данных»), блок не загрузился — `errHtml()`.

- Варианты иконки «глаз в треугольнике» в цветах схемы — `dev/design/logo.html` (`dev/design/logo/*.svg`).

## Правила проекта

- **Pydantic везде.** Любой запрос/ответ API — модель в `api/models/` (camelCase-алиасы,
  `extra="ignore"`, описываем только нужные поля). Данные во фронт — модели `domain/models.py`
  (`to_js()`). Словари-«мешки» не заводить.
- **Типизация и docstring у всех функций** (ruff `ANN` + `D`, mypy strict). `print` запрещён — `logging`.
- **Комментарии в коде не удалять** (`agents.md: preserve_comments = true`).
- **Единый дизайн UI.** Всё строится из `ui/css/components.css`: `.skeleton` (shimmer для
  загружающихся значений — мерцает значение, а не подпись), `.busy .shimmer-target` (обновление блока),
  `.corner-btn` (↻ в углу карточки), `[data-tip]` (подсказка), `button.icon`/`.square`, `.copyable`,
  `.na`, `.modal`, `.sheet` (большое окно-лист), `.table` (липкая шапка), `.chip`, `.check`, `.badge`,
  `.alarm`, `.card`, `.kv`/`.kv-grid`, `.changelog`. Цвета — только переменные из `tokens.css`.
  Нужен новый элемент — сначала добавить компонент туда, потом использовать.
- Проверка UI без браузера: `uv run python -m dev.ui_check @steps.txt` (шаги `wait:/click:/type:/js:/snap:`,
  `win:N` — перейти в окно N, `title` — напечатать document.title окна).
- **Коммиты — Conventional Commits на русском**, один коммит на одно изменение:
  `feat: …` (новая функция → minor), `fix: …` (→ patch), `refactor/test/ci/docs/chore: …` (версию не
  меняют, в changelog не попадают), `feat(dev): …` — инструменты разработчика (в changelog не идут).
  Текст `feat`/`fix` — это changelog, который увидит пользователь в окне обновления: пиши по-человечески.
- **Не пушить**, пока пользователь сам не скажет (он проверяет результат глазами).
- Новые зависимости — только с согласия пользователя (`install_dependencies = "ask"`).
- Все изменения и новые договорённости — дописывать в этот файл.

## Версии и релизы

Версию руками не трогаем. Релиз: GitHub → Actions → **Release** → Run workflow. CI прогоняет проверки,
`git cliff --bumped-version` считает версию по коммитам с последнего тега, changelog из `feat`/`fix`
становится текстом GitHub Release, который программа показывает в окне «Доступно обновление».
Локально версия = `git describe` + `-dev`; проверка обновлений в dev-сборке выключена.

## API Пирамиды (шпаргалка)

База: `https://s00-pml-web1.hq.vlmrk.corp:8080/api/v1` (доступна только из корпоративной сети).
Авторизация: `POST auth/login/?timeZoneOffset=-240` → `tokens.accessToken` → `Authorization: Bearer`.

ID: у прибора свой id (`getinstances → data[0].id`, «meter id»), у точки учёта — `data[0]["-8295"].id`
(«instance id», «point id»). Почти все запросы — по **point id**. Исключение: опрос реле
`startasynctaskreadloadlimitstates {metersId: [meter id]}`. В журнале событий (`geteventsforobjects.ids`
и `startreadeventsasync.eventSourcesIntRefNames`) — point id (договорились; проверить на проде).

| Что | Запрос |
|-----|--------|
| Поиск ПУ | `POST rdinstance/getinstances/` (classId -1646, filter `["-1494","contains",num]`, take 2) |
| Договор, адрес | `GET rdinstance/getinstanceinfo/?instanceId=` (`-10024` ЛС, `-13379` путь) |
| Показания | `POST meterdata/read/` (classifierId 2481, параметры см. `meterdata.py`) |
| Опрос показаний | `POST meterdata/acquire/` → id задачи → поллинг → снова `read` |
| Реле и лимит | `POST loadlimitmanagement/getmeterpointswithloadandlimitstate/` |
| Опрос реле | `POST loadlimitmanagement/startasynctaskreadloadlimitstates/` |
| Журнал | `POST events/geteventsforobjects/` (интервал — 10 лет назад) |
| Вычитать журнал | `POST events/startreadeventsasync/` (с последнего события до сейчас) |
| Задачи | `GET backgroundtasks/getbackgroundtask/?backgroundTaskId=` (1-й раз), затем `getbackgroundtaskstate/?…&logType=2` |
| Почасовка | `POST reports/createfilereportasync/?reportId=12290958&reportFormatDataId=-7128` → задача → `getarchivereport` |

Дата состояния реле/лимита: после утреннего опроса — `valueDt`, после ручного — `valueDt=null`, дата в
`lastSuccessReadOperation.dt`. Отмена задачи на сервере неизвестна — отмена в программе лишь прекращает ожидание.

## Эмулятор (`dev/mock_server`)

Те же пути и форматы. Логин любой, пароль `wrong` — ошибка. Сценарии по номеру ПУ:
`000` — не найден, `111` — несколько, `222` — без опросов, `333` — 3 маршрута, `555` — реле отключено,
`777` — тревожные события, `999` — опрос ~40 с с ошибкой (проверка отмены), остальное — обычный ПУ.
Учётки эмулятора хранятся отдельно (`SimplePyramid-Emulator`) и не смешиваются с боевыми.

## Тесты

`tests/unit` — модели, домен, xlsx, утилиты; `tests/integration` — клиент (respx), сервис и мост поверх
эмулятора в памяти (`httpx.ASGITransport`). Сценарии выбора показаний — `tests/data/readings_scenarios.json`
(новый кейс = новая запись). Тестовые данные обезличены — реальные ФИО/адреса/телефоны не коммитить.

## TODO / Roadmap

- [ ] Начало интервала журнала событий привязать к дате ввода точки/ПУ (кандидат — `-1498` в getinstances).
- [ ] Проверить на проде: id для событий, формат ответов реле после ручного опроса.
- [ ] (идея, `???`) Модуль «опросить все наши счётчики» с поиском по номеру и мгновенным показом показаний.
