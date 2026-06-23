from __future__ import annotations

import os
from datetime import date, datetime, timedelta
from typing import Any
from zoneinfo import ZoneInfo

try:
    from fastapi import HTTPException
except ImportError:  # pragma: no cover
    class HTTPException(Exception):
        def __init__(self, status_code: int, detail: str):
            super().__init__(detail)
            self.status_code = status_code
            self.detail = detail

DEFAULT_TZ = os.environ.get("TIMEZONE", "UTC")
MAX_DATE_RANGE_DAYS = int(os.environ.get("MAX_DATE_RANGE_DAYS", "366"))


def now_local(tz_name: str = DEFAULT_TZ) -> datetime:
    return datetime.now(ZoneInfo(tz_name))


def parse_local_day(value: str | None, default: date) -> date:
    if not value:
        return default
    return date.fromisoformat(value)


def parse_api_day(value: str | None, default: date, field_name: str) -> date:
    try:
        return parse_local_day(value, default)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=f"{field_name} must be YYYY-MM-DD") from exc


def parse_local_datetime(value: str | None, default: datetime, tz_name: str = DEFAULT_TZ) -> datetime:
    if not value:
        return default
    if value.endswith("Z"):
        value = value[:-1] + "+00:00"
    parsed = datetime.fromisoformat(value)
    tz = ZoneInfo(tz_name)
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=tz)
    return parsed.astimezone(tz)


def parse_api_datetime(value: str | None, default: datetime, field_name: str, tz_name: str = DEFAULT_TZ) -> datetime:
    try:
        return parse_local_datetime(value, default, tz_name)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=f"{field_name} must be ISO datetime") from exc


def validate_date_range(start: date, end: date) -> None:
    if start > end:
        raise HTTPException(status_code=400, detail="date_from must be before date_to")
    if (end - start).days + 1 > MAX_DATE_RANGE_DAYS:
        raise HTTPException(status_code=400, detail=f"date range may not exceed {MAX_DATE_RANGE_DAYS} days")


def validate_datetime_range(start_at: datetime, end_at: datetime) -> None:
    if start_at >= end_at:
        raise HTTPException(status_code=400, detail="start_at must be before end_at")
    if (end_at - start_at).total_seconds() > MAX_DATE_RANGE_DAYS * 86_400:
        raise HTTPException(status_code=400, detail=f"datetime range may not exceed {MAX_DATE_RANGE_DAYS} days")


def week_start(day: date) -> date:
    return day - timedelta(days=day.weekday())


def month_start(day: date) -> date:
    return day.replace(day=1)


def previous_month_bounds(day: date) -> tuple[date, date]:
    first_this_month = month_start(day)
    last_previous_month = first_this_month - timedelta(days=1)
    return month_start(last_previous_month), last_previous_month


def period_bounds(period: str, today: date) -> tuple[date, date]:
    if period == "today":
        return today, today
    if period == "week":
        return week_start(today), today
    if period == "month":
        return month_start(today), today
    raise ValueError(f"unknown period: {period}")


def iter_days(start: date, end: date):
    day = start
    while day <= end:
        yield day
        day += timedelta(days=1)


def float_setting(settings: dict[str, str], key: str, default: float) -> float:
    try:
        return float(settings.get(key, default))
    except (TypeError, ValueError):
        return default


def bool_setting(settings: dict[str, str], key: str, default: bool = False) -> bool:
    value = str(settings.get(key, str(default))).lower()
    return value in {"1", "true", "yes", "on"}
