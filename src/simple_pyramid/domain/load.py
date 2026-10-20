"""Состояние нагрузки (реле) и лимита мощности."""

from datetime import datetime

from simple_pyramid.api.models.loadlimit import LimitState, LoadLimitPoint, LoadState
from simple_pyramid.domain.models import LoadInfo


def _latest(*values: datetime | None) -> datetime | None:
    """Самая свежая из непустых дат."""
    present = [v for v in values if v is not None]
    return max(present) if present else None


def _state_dt(state: LoadState | LimitState) -> datetime | None:
    """Дата состояния.

    После ежедневного опроса дата лежит в ``valueDt``, а после ручного обновления
    ``valueDt`` = null и дата — в ``lastSuccessReadOperation.dt``.
    """
    op = state.last_success_read_operation
    return _latest(state.value_dt, op.dt if op else None)


def relay_is_on(caption: str | None) -> bool | None:
    """«Включено» → True, «Отключено/Выключено» → False, иначе None."""
    if not caption:
        return None
    text = caption.strip().lower()
    if text.startswith("включ"):
        return True
    if text.startswith(("отключ", "выключ")):
        return False
    return None


def build_load_info(points: list[LoadLimitPoint]) -> LoadInfo:
    """Собирает состояние реле и лимит для первой точки ответа."""
    if not points:
        return LoadInfo()
    point = points[0]
    relay = relay_at = limit = limit_at = None
    if point.load_state is not None:
        relay = point.load_state.value.caption if point.load_state.value else None
        relay_at = _state_dt(point.load_state)
    if point.limit_state is not None:
        limit = point.limit_state.value
        limit_at = _state_dt(point.limit_state)
    return LoadInfo(
        relay=relay,
        relay_on=relay_is_on(relay),
        relay_at=relay_at,
        limit=limit,
        limit_kw=round(limit / 1000, 3) if limit is not None else None,
        limit_at=limit_at,
    )
