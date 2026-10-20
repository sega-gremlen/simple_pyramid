"""Мост JS ↔ Python поверх эмулятора: события, отмена, выгрузки, вход."""

import time
from concurrent.futures import Future
from datetime import date, timedelta

import httpx
import pytest

from simple_pyramid.api.client import PyramidClient
from simple_pyramid.desktop.bridge import Api
from simple_pyramid.desktop.credentials import CredentialStore
from simple_pyramid.desktop.runner import AsyncRunner
from simple_pyramid.services.sink import RecordingSink
from tests.unit.test_desktop_utils import MemoryKeyring


class FakeWindow:
    def __init__(self, folder):
        self.titles = []
        self.heights = []
        self.closed = False
        self.folder = folder
        self.children = {}
        self.dialog_owner = None
        self.cancel_dialog = False

    def set_title(self, title):
        self.titles.append(title)

    def grow_height(self, delta):
        self.heights.append(delta)

    def choose_folder(self, kind=None):
        self.dialog_owner = kind
        return None if self.cancel_dialog else str(self.folder)

    def open_child(self, kind, title):
        self.children[kind] = title

    def set_child_title(self, kind, title):
        if kind in self.children:
            self.children[kind] = title

    def close(self):
        self.closed = True


def wait_until(predicate, timeout=5.0):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if predicate():
            return
        time.sleep(0.01)
    raise AssertionError("условие не выполнилось")


@pytest.fixture
def bridge(settings, mock_app, tmp_path):
    runner = AsyncRunner()
    sink = RecordingSink()
    client = PyramidClient(settings, transport=httpx.ASGITransport(app=mock_app))
    api = Api(
        settings, sink, runner=runner, client=client,
        credentials=CredentialStore(backend=MemoryKeyring()),
    )  # fmt: skip
    window = FakeWindow(tmp_path)
    api._attach_window(window)
    api.sink, api.window = sink, window  # type: ignore[attr-defined]
    yield api
    runner.stop()


def login(bridge):
    bridge.login("samara\\FilippovAS", "pwd")
    wait_until(lambda: bridge.sink.of("Auth"))
    assert bridge.sink.of("Auth")[-1] == {"ok": True, "login": "FilippovAS"}


def test_bootstrap_without_saved_login(bridge):
    info = bridge.bootstrap()
    assert info["state"] == "need_login"
    assert info["version"]


def test_login_saves_and_sets_title(bridge):
    login(bridge)
    assert bridge.window.titles[-1] == "Простая Пирамида • FilippovAS"
    assert bridge._creds.load() == ("samara\\FilippovAS", "pwd")
    info = bridge.bootstrap()  # следующий запуск — автовход
    assert info["state"] == "logging_in"
    assert info["login"] == "FilippovAS"


def test_login_wrong_password(bridge):
    bridge.login("user", "wrong")
    wait_until(lambda: bridge.sink.of("Auth"))
    assert bridge.sink.of("Auth")[-1]["ok"] is False


def test_logout(bridge):
    login(bridge)
    bridge.logout()
    assert bridge._creds.load() is None
    assert bridge.sink.of("Auth")[-1]["ok"] is False
    assert bridge.window.titles[-1] == "Простая Пирамида"  # после выхода — без логина


def test_search_flow(bridge):
    login(bridge)
    bridge.search("  021250611469 ")
    wait_until(
        lambda: any(
            s["kind"] == "ok" and "Все данные" in s["text"] for s in bridge.sink.of("Status")
        )
    )
    assert bridge.sink.of("SearchStarted") == [{"meterNum": "021250611469"}]
    wait_until(lambda: any(p["state"] != "wait" for p in bridge.sink.of("Ping")))
    page = bridge.events_page(0, 10, True)
    assert page["items"]
    assert bridge.events_page(0, 10_000, False)["items"].__len__() <= 100


def test_search_empty_and_not_found(bridge):
    login(bridge)
    bridge.search("   ")
    assert bridge.sink.of("Status")[-1]["kind"] == "warn"
    bridge.search("000")
    wait_until(lambda: bridge.sink.of("SearchFailed"))
    assert bridge.sink.of("Status")[-1]["kind"] == "warn"
    assert not bridge.sink.of("Error")


def test_search_without_login_shows_error(bridge):
    bridge.search("021250611469")
    wait_until(lambda: bridge.sink.of("SearchFailed"))
    assert bridge.sink.of("Error")[-1]["title"] == "Ошибка входа"


def test_refresh_and_cancel(bridge, mock_app):
    login(bridge)
    bridge.search("021250611469")
    wait_until(lambda: any("Все данные" in s["text"] for s in bridge.sink.of("Status")))
    assert bridge.refresh("unknown") is False
    assert bridge.cancel("readings") is False

    original = mock_app.state.mock.add_task

    def slow(task):
        task.duration = 60
        return original(task)

    mock_app.state.mock.add_task = slow
    assert bridge.refresh("readings") is True
    wait_until(lambda: bridge.sink.of("SectionBusy"))
    assert bridge.cancel("readings") is True
    wait_until(lambda: bridge.sink.of("SectionBusy")[-1]["busy"] is False)


def test_period_validation_and_daily(bridge):
    assert bridge.daily_view("01.10.2026", "02.10.2026")["ok"] is False  # прибор не открыт
    login(bridge)
    bridge.search("021250611469")
    wait_until(lambda: any("Все данные" in s["text"] for s in bridge.sink.of("Status")))
    assert bridge.validate_period("67.10.2026", "01.10.2026")["ok"] is False
    end = date.today()
    start = end - timedelta(days=3)
    period = (start.strftime("%d.%m.%Y"), end.strftime("%d.%m.%Y"))
    assert bridge.validate_period(*period) == {"ok": True, "days": 4}
    view = bridge.daily_view(*period)
    assert view["ok"] is True
    assert len(view["rows"]) == 4
    assert bridge.daily_view("bad", "bad")["ok"] is False


def test_export(bridge, tmp_path):
    login(bridge)
    bridge.search("021250611469")
    wait_until(lambda: any("Все данные" in s["text"] for s in bridge.sink.of("Status")))
    today = date.today().strftime("%d.%m.%Y")
    assert bridge.export("daily", today, today, str(tmp_path / "нет такой"))["ok"] is False
    assert bridge.export("daily", "x", today, str(tmp_path))["ok"] is False
    assert bridge.export("daily", today, today, str(tmp_path)) == {"ok": True}
    wait_until(lambda: any(e["stage"] == "done" for e in bridge.sink.of("Export")))
    done = next(e for e in bridge.sink.of("Export") if e["stage"] == "done")
    assert done["path"].endswith(".xlsx")
    assert bridge.browse_folder() == str(tmp_path)


def test_window_helpers(bridge):
    bridge.fit_height(1)  # меньше порога — игнор
    bridge.fit_height(-40)
    assert bridge.window.heights == [-40]
    bridge.close()
    assert bridge.window.closed


def test_spawn_reports_unexpected_errors(bridge):
    async def boom():
        raise RuntimeError("неожиданно")

    future: Future = bridge._spawn("x", boom())
    wait_until(future.done)
    wait_until(lambda: bridge.sink.of("Error"))
    assert bridge.sink.of("Error")[-1]["title"] == "Внутренняя ошибка"


def test_child_windows(bridge):
    assert bridge.open_daily() is False  # прибор не открыт
    assert bridge.window_context() == {"meter": None}
    login(bridge)
    bridge.search("021250611469")
    wait_until(lambda: any("Все данные" in s["text"] for s in bridge.sink.of("Status")))
    assert bridge.open_daily() is True
    assert bridge.open_events(False) is True
    assert bridge.window.children["daily"].startswith("Подневка • ")
    assert "№021250611469" in bridge.window.children["events"]
    assert bridge.sink.of("EventsFilter")[-1] == {"importantOnly": False}
    ctx = bridge.window_context()
    assert ctx["meter"]["meterNum"] == "021250611469"
    assert ctx["importantOnly"] is False
    assert ctx["eventsLoaded"] is True
    # новый прибор — заголовки открытых окон обновляются
    bridge.search("5551")
    wait_until(lambda: "№5551" in bridge.window.children["daily"])


def test_export_here(bridge, tmp_path):
    login(bridge)
    bridge.search("021250611469")
    wait_until(lambda: any("Все данные" in s["text"] for s in bridge.sink.of("Status")))
    today = date.today().strftime("%d.%m.%Y")
    assert bridge.export_here("daily", "bad", today, "daily")["ok"] is False
    bridge.window.cancel_dialog = True
    assert bridge.export_here("daily", today, today, "daily") == {"ok": False, "cancelled": True}
    bridge.window.cancel_dialog = False
    assert bridge.export_here("daily", today, today, "daily") == {"ok": True}
    assert bridge.window.dialog_owner == "daily"
    wait_until(lambda: any(e["stage"] == "done" for e in bridge.sink.of("Export")))
    done = next(e for e in bridge.sink.of("Export") if e["stage"] == "done")
    assert done["source"] == "daily"
