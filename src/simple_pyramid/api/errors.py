"""Исключения работы с API. Текст ``str(exc)`` показывается пользователю."""


class PyramidError(Exception):
    """Базовая ошибка: всё, что можно показать пользователю как понятное сообщение."""

    title = "Ошибка"

    def __init__(self, message: str, *, details: str | None = None) -> None:
        super().__init__(message)
        self.details = details


class AuthError(PyramidError):
    """Не удалось войти (неверный логин/пароль или нет сохранённых учётных данных)."""

    title = "Ошибка входа"


class ConnectionFailedError(PyramidError):
    """Сервер недоступен (нет сети, VPN, таймаут)."""

    title = "Нет связи с сервером"


class ApiError(PyramidError):
    """Сервер ответил ошибкой (4xx/5xx)."""

    title = "Ошибка сервера"

    def __init__(self, status_code: int, message: str, *, details: str | None = None) -> None:
        super().__init__(message, details=details)
        self.status_code = status_code


class UnexpectedResponseError(PyramidError):
    """Ответ сервера не совпал с ожидаемой моделью (изменился формат API)."""

    title = "Неожиданный ответ сервера"


class MeterNotFoundError(PyramidError):
    """Прибор с таким номером не найден."""

    title = "Прибор не найден"


class AmbiguousMeterError(PyramidError):
    """По номеру найдено больше одного прибора."""

    title = "Найдено несколько приборов"


class TaskTimeoutError(PyramidError):
    """Фоновая задача не завершилась за отведённое время."""

    title = "Задача не завершилась"
