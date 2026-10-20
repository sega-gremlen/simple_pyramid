"""Модели авторизации."""

from simple_pyramid.api.models.base import ApiModel


class LoginRequest(ApiModel):
    """Тело запроса ``POST /auth/login/``."""

    username: str
    password: str
    tokens: None = None


class Tokens(ApiModel):
    """Токены из ответа на логин."""

    access_token: str


class LoginResponse(ApiModel):
    """Ответ на логин: токен и id пользователя (нужен для скачивания отчётов)."""

    tokens: Tokens
    user_id: int | str | None = None
