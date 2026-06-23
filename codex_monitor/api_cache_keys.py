from __future__ import annotations

import os
from datetime import date, datetime, timedelta, timezone
from urllib.parse import quote
from typing import Any

from .api_dates import now_local

TODAY_CACHE_TTL_SECONDS = int(os.environ.get("TODAY_CACHE_TTL_SECONDS", "90"))
HISTORIC_CACHE_TTL_SECONDS = int(os.environ.get("HISTORIC_CACHE_TTL_SECONDS", str(7 * 24 * 60 * 60)))
LIVE_WINDOW_CACHE_BUCKET_SECONDS = int(os.environ.get("LIVE_WINDOW_CACHE_BUCKET_SECONDS", "60"))


def response_cache_meta(hit: bool, ttl_seconds: int) -> dict[str, Any]:
    return {
        "hit": hit,
        "ttl_seconds": ttl_seconds,
        "served_at": datetime.now(timezone.utc).isoformat(),
    }


def period_includes_today(start: date, end: date, today: date | None = None) -> bool:
    today = today or now_local().date()
    return start <= today <= end


def ttl_for_range(start: date, end: date) -> int:
    if period_includes_today(start, end):
        return TODAY_CACHE_TTL_SECONDS
    return HISTORIC_CACHE_TTL_SECONDS


def window_includes_today(start_at: datetime, end_at: datetime, today: date | None = None) -> bool:
    local_now = now_local()
    today = today or local_now.date()
    local_start = start_at.astimezone(local_now.tzinfo).date()
    inclusive_end = end_at - timedelta(microseconds=1)
    local_end = inclusive_end.astimezone(local_now.tzinfo).date()
    return period_includes_today(local_start, local_end, today)


def ttl_for_window(start_at: datetime, end_at: datetime) -> int:
    if window_includes_today(start_at, end_at):
        return TODAY_CACHE_TTL_SECONDS
    return HISTORIC_CACHE_TTL_SECONDS


def account_cache_part(account_filter: set[str] | None) -> str:
    if not account_filter:
        return "all"
    return ",".join(sorted(account_filter))


def window_cache_part(value: datetime) -> str:
    utc_value = value.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")
    return quote(utc_value, safe="")


def bucket_window_end_for_cache(value: datetime) -> datetime:
    bucket_seconds = max(LIVE_WINDOW_CACHE_BUCKET_SECONDS, 1)
    utc_value = value.astimezone(timezone.utc)
    bucketed_timestamp = int(utc_value.timestamp()) // bucket_seconds * bucket_seconds
    return datetime.fromtimestamp(bucketed_timestamp, timezone.utc).astimezone(value.tzinfo)


def snapshot_cache_key(day: date) -> str:
    return f"snapshot:v7:{day.isoformat()}"


def latest_snapshot_cache_key() -> str:
    return "snapshot-latest:v1"


def account_limit_statuses_cache_key() -> str:
    return "account-limit-statuses:v1"


def versioned_cache_key(generation: int | str, key: str) -> str:
    return f"generation:{generation}:{key}"


def report_cache_key(start: date, end: date, account_filter: set[str] | None = None) -> str:
    return f"report:v9:{start.isoformat()}:{end.isoformat()}:{account_cache_part(account_filter)}"


def report_window_cache_key(start_at: datetime, end_at: datetime, account_filter: set[str] | None = None) -> str:
    return f"report-window:v3:{window_cache_part(start_at)}:{window_cache_part(end_at)}:{account_cache_part(account_filter)}"


def days_cache_key(start: date, end: date, account_filter: set[str] | None = None) -> str:
    return f"days:v9:{start.isoformat()}:{end.isoformat()}:{account_cache_part(account_filter)}"


def days_window_cache_key(start_at: datetime, end_at: datetime, account_filter: set[str] | None = None) -> str:
    return f"days-window:v3:{window_cache_part(start_at)}:{window_cache_part(end_at)}:{account_cache_part(account_filter)}"


def diagnostics_cache_key(start: date, end: date, account_filter: set[str] | None = None) -> str:
    return f"diagnostics:v1:{start.isoformat()}:{end.isoformat()}:{account_cache_part(account_filter)}"


def diagnostics_window_cache_key(start_at: datetime, end_at: datetime, account_filter: set[str] | None = None) -> str:
    return f"diagnostics-window:v1:{window_cache_part(start_at)}:{window_cache_part(end_at)}:{account_cache_part(account_filter)}"


def day_cache_key(day: date, account_filter: set[str] | None = None) -> str:
    return f"day:v8:{day.isoformat()}:{account_cache_part(account_filter)}"


def session_history_cache_key(start: date, end: date, account_filter: set[str] | None = None) -> str:
    return f"sessions:v8:{start.isoformat()}:{end.isoformat()}:{account_cache_part(account_filter)}"


def session_history_window_cache_key(start_at: datetime, end_at: datetime, account_filter: set[str] | None = None) -> str:
    return f"sessions-window:v4:{window_cache_part(start_at)}:{window_cache_part(end_at)}:{account_cache_part(account_filter)}"


def session_detail_cache_key(session_id: str, start: date, end: date, account_filter: set[str] | None = None) -> str:
    return f"session:v8:{quote(session_id, safe='')}:{start.isoformat()}:{end.isoformat()}:{account_cache_part(account_filter)}"


def session_detail_window_cache_key(session_id: str, start_at: datetime, end_at: datetime, account_filter: set[str] | None = None) -> str:
    return f"session-window:v4:{quote(session_id, safe='')}:{window_cache_part(start_at)}:{window_cache_part(end_at)}:{account_cache_part(account_filter)}"


def ttl_for_day(day: date) -> int:
    if day == now_local().date():
        return TODAY_CACHE_TTL_SECONDS
    return HISTORIC_CACHE_TTL_SECONDS
