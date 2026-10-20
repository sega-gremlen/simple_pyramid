"""Десктоп-утилиты: хранилище паролей, пинг, обновления, emitter, версия."""

import asyncio
import pickle

import httpx
import pytest
import respx
from keyring.errors import KeyringError

from simple_pyramid.desktop import pinger
from simple_pyramid.desktop.bridge import short_login, window_title
from simple_pyramid.desktop.credentials import CredentialStore
from simple_pyramid.desktop.emitter import WindowEmitter, build_script
from simple_pyramid.desktop.updater import check_update, download_update, is_newer
from simple_pyramid.version import display_version, is_dev_build


class MemoryKeyring:
    """Подмена keyring в памяти."""

    def __init__(self, fail: bool = False) -> None:
        self.store: dict[tuple[str, str], str] = {}
        self.fail = fail

    def _check(self):
        if self.fail:
            raise KeyringError("boom")

    def get_password(self, service, user):
        self._check()
        return self.store.get((service, user))

    def set_password(self, service, user, password):
        self._check()
        self.store[(service, user)] = password

    def delete_password(self, service, user):
        self._check()
        self.store.pop((service, user), None)


# ---------------------------------------------------------------- credentials
def test_credentials_roundtrip():
    store = CredentialStore(backend=MemoryKeyring())
    assert store.load() is None
    store.save("FilippovAS", "secret")
    assert store.load() == ("FilippovAS", "secret")
    store.clear()
    assert store.load() is None


def test_credentials_migrate_legacy_pickle(tmp_path):
    legacy = tmp_path / "pyramid_creds.pkl"
    legacy.write_bytes(pickle.dumps({"login": "old", "password": "pwd"}))
    kr = MemoryKeyring()
    store = CredentialStore(legacy, backend=kr)
    assert store.load() == ("old", "pwd")
    assert not legacy.exists()  # пароль больше не лежит открытым текстом


def test_credentials_broken_legacy_file(tmp_path):
    legacy = tmp_path / "pyramid_creds.pkl"
    legacy.write_bytes(b"not a pickle")
    store = CredentialStore(legacy, backend=MemoryKeyring())
    assert store.load() is None


def test_credentials_keyring_errors_are_swallowed():
    store = CredentialStore(backend=MemoryKeyring(fail=True))
    store.save("a", "b")
    store.clear()
    assert store.load() is None


def test_credentials_services_are_separate():
    kr = MemoryKeyring()
    CredentialStore(backend=kr, service="A").save("u", "p")
    assert CredentialStore(backend=kr, service="B").load() is None


# ---------------------------------------------------------------- ping
async def test_ping_until_success_counts_attempts():
    results = iter([False, False, True])
    attempts = []

    async def fake_ping(ip):
        return next(results)

    ok = await pinger.ping_until_success(
        "10.0.0.1", max_attempts=5, on_attempt=lambda a, t: attempts.append((a, t)),
        ping=fake_ping, pause=0,
    )  # fmt: skip
    assert ok == 3
    assert attempts == [(1, 5), (2, 5), (3, 5)]


async def test_ping_until_success_gives_up():
    async def fake_ping(ip):
        raise TimeoutError

    assert await pinger.ping_until_success("x", max_attempts=2, ping=fake_ping, pause=0) is None


def test_ping_command():
    cmd = pinger.ping_command("10.0.0.1")
    assert cmd[0] == "ping"
    assert cmd[-1] == "10.0.0.1"


async def test_ping_once_localhost():
    assert await pinger.ping_once("127.0.0.1") is True


# ---------------------------------------------------------------- updater
GITHUB = "https://api.github.com/repos/sega-gremlen/simple_pyramid/releases/latest"


@pytest.mark.parametrize(
    ("latest", "current", "expected"),
    [
        ("v1.4.0", "1.3.1", True),
        ("1.3.1", "1.3.1", False),
        ("v1.2.0", "1.3.0", False),
        ("bad", "1.0", False),
    ],
)
def test_is_newer(latest, current, expected):
    assert is_newer(latest, current) is expected


@respx.mock
async def test_check_update(settings, monkeypatch):
    monkeypatch.setattr("simple_pyramid.desktop.updater.is_dev_build", lambda: False)
    monkeypatch.setattr("simple_pyramid.desktop.updater.__version__", "1.3.1")
    respx.get(GITHUB).respond(
        json={"tag_name": "v1.4.0", "body": "## Новое\n- статус реле", "assets": [
            {"browser_download_url": "https://example.test/simple_pyramid.exe"}]}
    )  # fmt: skip
    info = await check_update(settings)
    assert info is not None
    assert info.version == "1.4.0"
    assert "статус реле" in info.changelog


@respx.mock
async def test_check_update_no_update_or_error(settings, monkeypatch):
    monkeypatch.setattr("simple_pyramid.desktop.updater.is_dev_build", lambda: False)
    monkeypatch.setattr("simple_pyramid.desktop.updater.__version__", "9.9.9")
    respx.get(GITHUB).respond(json={"tag_name": "v1.4.0", "assets": []})
    assert await check_update(settings) is None
    respx.get(GITHUB).respond(500)
    assert await check_update(settings) is None


async def test_check_update_skipped_for_dev_build(settings):
    assert is_dev_build()
    assert await check_update(settings) is None


@respx.mock
async def test_download_update_retries_then_saves(settings, tmp_path):
    route = respx.get(settings.fallback_exe_url)
    route.side_effect = [
        httpx.ConnectError("нет сети"),
        httpx.Response(503),
        httpx.Response(200, content=b"MZ" * 1000, headers={"content-length": "2000"}),
    ]
    statuses, progress = [], []
    path = await download_update(
        settings, tmp_path, retry_pause=0,
        on_status=lambda m, a: statuses.append(a), on_progress=lambda p, d, t: progress.append(p),
    )  # fmt: skip
    assert path.read_bytes() == b"MZ" * 1000
    assert path.name == "simple_pyramid_update.exe"
    assert statuses == [1, 1, 2, 2, 3, 0]
    assert progress[-1] == 100


# ---------------------------------------------------------------- emitter / title / version
def test_build_script_escapes_payload():
    script = build_script("Status", {"text": 'кавычки " и </script>'})
    assert script.startswith("window.onStatus && window.onStatus(")
    assert '\\"' in script


def test_window_emitter():
    calls = []

    class Win:
        def run_js(self, script):
            calls.append(script)

    emitter = WindowEmitter()
    emitter.emit("Status", {})  # окна ещё нет — молча теряем
    emitter.window = Win()
    emitter.emit("Ping", {"id": "r0"})
    assert calls == ['window.onPing && window.onPing({"id": "r0"})']

    class Broken:
        def run_js(self, script):
            raise RuntimeError("окно закрыто")

    emitter.window = Broken()
    emitter.emit("Status", {})  # не падает

    # несколько окон: событие уходит во все, закрытое окно отключается
    first, second = Win(), Win()
    emitter.window = first
    emitter.add(second)
    calls.clear()
    emitter.emit("Status", {})
    assert len(calls) == 2
    emitter.remove(second)
    emitter.emit("Status", {})
    assert len(calls) == 3
    assert emitter.window is first
    emitter.window = None
    assert emitter.window is None


def test_window_title_and_short_login():
    assert short_login("samara.vlmrk.corp\\FilippovAS") == "FilippovAS"
    assert short_login(None) is None
    assert window_title("FilippovAS", mock=False) == "Простая Пирамида • FilippovAS"
    assert window_title(None, mock=True) == "Простая Пирамида • ЭМУЛЯТОР"


def test_display_version_dev():
    assert display_version().endswith("-dev") or display_version() == "dev"


async def test_runner_runs_coroutines():
    from simple_pyramid.desktop.runner import AsyncRunner

    runner = AsyncRunner()

    async def double(x):
        await asyncio.sleep(0)
        return x * 2

    assert await asyncio.wrap_future(runner.submit(double(21))) == 42
    runner.stop()


# ---------------------------------------------------------------- «Что нового»
TAG_URL = "https://api.github.com/repos/sega-gremlen/simple_pyramid/releases/tags/v1.4.0"


def test_release_tag_url(settings):
    from simple_pyramid.desktop.updater import release_tag_url

    assert release_tag_url(settings, "v1.4.0") == TAG_URL


@respx.mock
async def test_whats_new_shown_once(settings, tmp_path, monkeypatch):
    from simple_pyramid.desktop.updater import SeenVersionStore, whats_new

    monkeypatch.setattr("simple_pyramid.desktop.updater.is_dev_build", lambda: False)
    route = respx.get(TAG_URL).respond(json={"tag_name": "v1.4.0", "body": "### Новое\n- Реле"})
    store = SeenVersionStore(tmp_path)
    info = await whats_new(settings, store, current="1.4.0")
    assert info is not None
    assert info.changelog == "### Новое\n- Реле"
    assert store.last_seen() == "1.4.0"
    assert await whats_new(settings, store, current="1.4.0") is None  # второй раз не показываем
    assert route.call_count == 1


@respx.mock
async def test_whats_new_network_error_retries_later(settings, tmp_path, monkeypatch):
    from simple_pyramid.desktop.updater import SeenVersionStore, whats_new

    monkeypatch.setattr("simple_pyramid.desktop.updater.is_dev_build", lambda: False)
    respx.get(TAG_URL).mock(side_effect=httpx.ConnectError("нет сети"))
    store = SeenVersionStore(tmp_path)
    assert await whats_new(settings, store, current="1.4.0") is None
    assert store.last_seen() is None


@respx.mock
async def test_whats_new_empty_body(settings, tmp_path, monkeypatch):
    from simple_pyramid.desktop.updater import SeenVersionStore, whats_new

    monkeypatch.setattr("simple_pyramid.desktop.updater.is_dev_build", lambda: False)
    respx.get(TAG_URL).respond(json={"tag_name": "v1.4.0", "body": ""})
    store = SeenVersionStore(tmp_path)
    assert await whats_new(settings, store, current="1.4.0") is None
    assert store.last_seen() == "1.4.0"


async def test_whats_new_dev_build(settings, tmp_path):
    from simple_pyramid.desktop.updater import SeenVersionStore, whats_new

    assert await whats_new(settings, SeenVersionStore(tmp_path)) is None


def test_seen_store_broken_file(tmp_path):
    from simple_pyramid.desktop.updater import SeenVersionStore

    (tmp_path / "state.json").write_text("{not json", encoding="utf-8")
    store = SeenVersionStore(tmp_path)
    assert store.last_seen() is None
    store.mark_seen("1.0.0")
    assert store.last_seen() == "1.0.0"
