"""Сборка доменных моделей прибора и точки учёта из ответов API."""

import re

from simple_pyramid.api.errors import AmbiguousMeterError, MeterNotFoundError
from simple_pyramid.api.models.instances import GetInstanceInfoResponse, GetInstancesResponse
from simple_pyramid.domain.models import MeterIdentity, PointInfo, Route

IP_RE = re.compile(r"\b(?:[0-9]{1,3}\.){3}[0-9]{1,3}\b")


def normalize_ip(raw_ip: str) -> str:
    """Убирает ведущие нули в октетах: ``010.010.020.030`` → ``10.10.20.30``.

    Без этого Windows-ping воспринимает октеты с нулём впереди как восьмеричные.
    """
    return ".".join(str(int(octet)) for octet in raw_ip.split("."))


def extract_ip(text: str) -> tuple[str, str] | None:
    """Ищет IP-адрес в тексте маршрута.

    Returns:
        ``(ip_как_в_тексте, нормализованный_ip)`` или None, если IP нет.
    """
    match = IP_RE.search(text)
    if not match:
        return None
    raw = match.group(0)
    return raw, normalize_ip(raw)


def build_identity(meter_num: str, response: GetInstancesResponse) -> MeterIdentity:
    """Достаёт из ответа getinstances прибор, точку учёта и маршруты.

    Raises:
        MeterNotFoundError: прибор не найден.
        AmbiguousMeterError: найдено больше одного прибора.
    """
    if not response.data:
        raise MeterNotFoundError(
            "Прибора учёта с таким номером нет.\nПопробуйте убрать первый 0 в номере."
        )
    if len(response.data) > 1:
        raise AmbiguousMeterError("Найдено более одного прибора учёта.\nУточните номер.")

    meter = response.data[0]
    routes = []
    for i, ref in enumerate(meter.routes):
        ip = extract_ip(ref.caption)
        routes.append(
            Route(
                id=f"r{i}",
                text=ref.caption,
                ip=ip[1] if ip else None,
                ip_text=ip[0] if ip else None,
            )
        )
    return MeterIdentity(
        meter_num=meter_num,
        meter_id=meter.id,
        point_id=meter.point.id,
        model=meter.model,
        caption=meter.caption,
        point_caption=meter.point.caption,
        routes=routes,
    )


def build_point_info(response: GetInstanceInfoResponse) -> PointInfo:
    """Достаёт лицевой счёт (договор) и адрес точки учёта."""
    instance = response.instance
    account = instance.accounts[0].caption if instance.accounts else None
    account_number = None
    if account and "№" in account:
        account_number = account.split("№", 1)[1].strip() or None
    full_path = instance.full_path
    # Адрес — последний элемент иерархии
    address = full_path.split("/")[-1] if full_path else None
    return PointInfo(
        account=account,
        account_number=account_number,
        address=address,
        full_path=full_path,
    )
