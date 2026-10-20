"""Клиент API: авторизация, перелогин, ошибки, фоновые задачи."""

import asyncio

import httpx
import pytest
import respx

from simple_pyramid.api.client import PyramidClient
from simple_pyramid.api.errors import (
    ApiError,
    AuthError,
    ConnectionFailedError,
    TaskTimeoutError,
    UnexpectedResponseError,
)
from simple_pyramid.api.tasks import wait_for_task

BASE = "http://pyramid.test/api/v1"
LOGIN_OK = {"tokens": {"accessToken": "tok-1"}, "userId": 688}


@pytest.fixture
def respx_client(settings):
    return PyramidClient(settings)


@respx.mock
async def test_login_sets_bearer(respx_client):
    route = respx.post(f"{BASE}/auth/login/").respond(json=LOGIN_OK)
    await respx_client.login("user", "pwd")
    assert route.calls.last.request.url.params["timeZoneOffset"] == "-240"
    assert respx_client.authorized
    assert respx_client.user_id == 688
    info = respx.get(f"{BASE}/rdinstance/getinstanceinfo/").respond(json={"instance": {"id": 1}})
    await respx_client.get_instance_info(1)
    assert info.calls.last.request.headers["Authorization"] == "Bearer tok-1"
    assert info.calls.last.request.url.params["instanceId"] == "1"


@respx.mock
async def test_login_wrong_password(respx_client):
    respx.post(f"{BASE}/auth/login/").respond(400, text="bad")
    with pytest.raises(AuthError, match="Неверный логин"):
        await respx_client.login("user", "bad")
    assert not respx_client.authorized


@respx.mock
async def test_login_connection_error(respx_client):
    respx.post(f"{BASE}/auth/login/").mock(side_effect=httpx.ConnectError("no route"))
    with pytest.raises(ConnectionFailedError):
        await respx_client.login("user", "pwd")


@respx.mock
async def test_relogin_on_401_once_for_parallel_requests(respx_client):
    login = respx.post(f"{BASE}/auth/login/")
    login.side_effect = [
        httpx.Response(200, json=LOGIN_OK),
        httpx.Response(200, json={"tokens": {"accessToken": "tok-2"}, "userId": 688}),
    ]
    await respx_client.login("user", "pwd")

    def handler(request):
        if request.headers["Authorization"] == "Bearer tok-1":
            return httpx.Response(401)
        return httpx.Response(200, json={"instance": {"id": 7}})

    respx.get(f"{BASE}/rdinstance/getinstanceinfo/").mock(side_effect=handler)
    results = await asyncio.gather(*(respx_client.get_instance_info(7) for _ in range(3)))
    assert all(r.instance.id == 7 for r in results)
    assert login.call_count == 2  # перелогинились ровно один раз


@respx.mock
async def test_request_without_session(respx_client):
    with pytest.raises(AuthError, match="Нет активной сессии"):
        await respx_client.get_instance_info(1)


@respx.mock
async def test_api_error_and_bad_format(respx_client):
    respx.post(f"{BASE}/auth/login/").respond(json=LOGIN_OK)
    await respx_client.login("u", "p")
    respx.get(f"{BASE}/rdinstance/getinstanceinfo/").respond(500, text="Internal")
    with pytest.raises(ApiError) as exc:
        await respx_client.get_instance_info(1)
    assert exc.value.status_code == 500
    assert "Internal" in (exc.value.details or "")

    respx.get(f"{BASE}/rdinstance/getinstanceinfo/").respond(json={"wrong": True})
    with pytest.raises(UnexpectedResponseError) as bad:
        await respx_client.get_instance_info(1)
    assert "instance" in (bad.value.details or "")


@respx.mock
async def test_timeout_is_connection_error(respx_client):
    respx.post(f"{BASE}/auth/login/").respond(json=LOGIN_OK)
    await respx_client.login("u", "p")
    respx.get(f"{BASE}/rdinstance/getinstanceinfo/").mock(side_effect=httpx.ReadTimeout("slow"))
    with pytest.raises(ConnectionFailedError, match="не ответил"):
        await respx_client.get_instance_info(1)


async def test_logout(client):
    client.logout()
    assert not client.authorized
    assert client.username is None


# ---------------------------------------------------------------- фоновые задачи
@respx.mock
async def test_wait_for_task_reports_new_info_lines(respx_client, data):
    respx.post(f"{BASE}/auth/login/").respond(json=LOGIN_OK)
    await respx_client.login("u", "p")
    respx.get(f"{BASE}/backgroundtasks/getbackgroundtask/").respond(json=data("task_started.json"))
    state_route = respx.get(f"{BASE}/backgroundtasks/getbackgroundtaskstate/")
    state_route.side_effect = [
        httpx.Response(200, json=data("task_state_running.json")),
        httpx.Response(200, json=data("task_state_done.json")),
    ]
    lines: list[str] = []
    state = await wait_for_task(
        respx_client, -1876, interval=0, max_wait=5, on_log=lambda e: lines.append(e.message)
    )
    assert state.is_completed
    assert state_route.calls.last.request.url.params["logType"] == "2"
    # строки level=0 (Tx/Rx) отфильтрованы, повторно ничего не отдано
    assert lines == [
        "Начало выполнения задания",
        "Начало выполнения задания",
        "Установлено соединение Мегафон, +79000000000, 10.0.0.2, порт 5002",
        "По заданию 100340251 получено значение Состояние нагрузки Включено",
        "Ошибка выполнения запроса. Устройство вернуло ошибку: Объект неопределен",
        "По заданию 100340252 получено значение Ограничение нагрузки 15000",
        "Окончание выполнения задания",
    ]


@respx.mock
async def test_wait_for_task_timeout(respx_client, data):
    respx.post(f"{BASE}/auth/login/").respond(json=LOGIN_OK)
    await respx_client.login("u", "p")
    respx.get(f"{BASE}/backgroundtasks/getbackgroundtask/").respond(json=data("task_started.json"))
    respx.get(f"{BASE}/backgroundtasks/getbackgroundtaskstate/").respond(
        json=data("task_state_running.json")
    )
    with pytest.raises(TaskTimeoutError):
        await wait_for_task(respx_client, -1876, interval=0.01, max_wait=0.05)


async def test_unknown_meter_is_api_error(client):
    with pytest.raises(ApiError) as exc:
        await client.start_read_load_limit([1])  # прибора нет в эмуляторе
    assert exc.value.status_code == 404
