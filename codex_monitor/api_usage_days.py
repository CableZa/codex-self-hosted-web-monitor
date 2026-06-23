from __future__ import annotations

import asyncio
import json
from datetime import date, datetime, time, timedelta
from typing import Any

from . import api_usage as usage_facade
from .api_usage import (
    DEFAULT_TZ,
    MATERIALIZED_DAYS_BACK,
    cache,
    cacheable_window_end,
    day_cache_key,
    days_cache_key,
    days_report_has_activity,
    days_window_cache_key,
    fetch_usd_zar,
    iter_days,
    logger,
    month_start,
    now_local,
    previous_month_bounds,
    reset_window_for_datetime,
    resolve_window_reference_time,
    response_cache_meta,
    row_has_usage_activity,
    store,
    timed_dependency,
    ttl_for_day,
    ttl_for_range,
    ttl_for_window,
    usage_cache_generation,
    versioned_cache_key,
    week_start,
    window_dates,
)


DAY_ROLLUP_FIELDS = (
    "input_tokens",
    "cached_input_tokens",
    "uncached_input_tokens",
    "output_tokens",
    "reasoning_output_tokens",
    "total_tokens",
    "total_zar",
    "total_usd",
    "input_credits",
    "cached_input_credits",
    "output_credits",
    "reasoning_output_credits",
    "total_credits",
    "events",
    "sessions",
    "files",
)


def empty_day_row(day: date) -> dict[str, Any]:
    return {
        "day": day.isoformat(),
        "input_tokens": 0,
        "cached_input_tokens": 0,
        "uncached_input_tokens": 0,
        "output_tokens": 0,
        "reasoning_output_tokens": 0,
        "total_tokens": 0,
        "total_zar": 0,
        "total_usd": 0,
        "input_credits": 0,
        "cached_input_credits": 0,
        "output_credits": 0,
        "reasoning_output_credits": 0,
        "total_credits": 0,
        "events": 0,
        "sessions": 0,
        "files": 0,
    }


def month_end(day: date) -> date:
    if day.month == 12:
        return date(day.year, 12, 31)
    return date(day.year, day.month + 1, 1) - timedelta(days=1)


def empty_period_row(key: str, label: str, start_day: str, end_day: str) -> dict[str, Any]:
    row = empty_day_row(date.fromisoformat(start_day))
    row["day"] = key
    row["label"] = label
    row["start_day"] = start_day
    row["end_day"] = end_day
    return row


def add_day_to_period(target: dict[str, Any], row: dict[str, Any]) -> None:
    for field in DAY_ROLLUP_FIELDS:
        target[field] = target.get(field, 0) + (row.get(field, 0) or 0)


def rollup_day_rows(rows: list[dict[str, Any]], mode: str) -> list[dict[str, Any]]:
    grouped: dict[str, dict[str, Any]] = {}
    for row in rows:
        day = date.fromisoformat(str(row["day"]))
        if mode == "week":
            start = week_start(day)
            end = start + timedelta(days=6)
            key = start.isoformat()
            label = f"{start.isoformat()} to {end.isoformat()}"
        else:
            start = month_start(day)
            end = month_end(start)
            key = start.isoformat()[:7]
            label = key
        bucket = grouped.setdefault(key, empty_period_row(key, label, start.isoformat(), end.isoformat()))
        add_day_to_period(bucket, row)
    return [grouped[key] for key in sorted(grouped)]


def day_row_from_report(report: dict[str, Any], day: date, by_day: dict[str, dict[str, Any]] | None = None) -> dict[str, Any]:
    by_day = by_day or {row["day"]: row for row in report["by_day"]}
    row = by_day.get(day.isoformat(), {})
    if not row:
        return empty_day_row(day)
    return {
        "day": day.isoformat(),
        "input_tokens": row.get("input_tokens", 0),
        "cached_input_tokens": row.get("cached_input_tokens", 0),
        "uncached_input_tokens": row.get("uncached_input_tokens", 0),
        "output_tokens": row.get("output_tokens", 0),
        "reasoning_output_tokens": row.get("reasoning_output_tokens", 0),
        "total_tokens": row.get("total_tokens", 0),
        "total_zar": row.get("total_zar", 0),
        "total_usd": row.get("total_usd", 0),
        "input_credits": row.get("input_credits", 0),
        "cached_input_credits": row.get("cached_input_credits", 0),
        "output_credits": row.get("output_credits", 0),
        "reasoning_output_credits": row.get("reasoning_output_credits", 0),
        "total_credits": row.get("total_credits", 0),
        "events": row.get("events", 0),
        "sessions": row.get("sessions", 0),
        "files": row.get("files", 0),
    }


def rows_from_report(report: dict[str, Any], start: date, end: date) -> list[dict[str, Any]]:
    by_day = {row["day"]: row for row in report["by_day"]}
    return [day_row_from_report(report, day, by_day) for day in iter_days(start, end)]


async def cache_day_rows_from_report(
    report: dict[str, Any],
    start: date,
    end: date,
    account_filter: set[str] | None = None,
    generation: int | None = None,
) -> None:
    generation = await usage_cache_generation(generation)
    by_day = {row["day"]: row for row in report["by_day"]}
    today = now_local().date()
    for day in iter_days(start, end):
        row = day_row_from_report(report, day, by_day)
        if row_has_usage_activity(row) or day < today:
            await cache.set(versioned_cache_key(generation, day_cache_key(day, account_filter)), row, ttl_for_day(day))


async def cached_day_rows(
    start: date,
    end: date,
    account_filter: set[str] | None = None,
    generation: int | None = None,
) -> list[dict[str, Any]] | None:
    generation = await usage_cache_generation(generation)
    rows: list[dict[str, Any]] = []
    missing: list[str] = []
    for day in iter_days(start, end):
        row = await cache.get(versioned_cache_key(generation, day_cache_key(day, account_filter)))
        if not row:
            missing.append(day.isoformat())
            continue
        rows.append(row)
    if missing:
        logger.info("daily_cache_miss count=%s days=%s", len(missing), ",".join(missing[:10]))
        return None
    return rows


async def ensure_daily_cache_for_range(
    start: date,
    end: date,
    account_filter: set[str] | None = None,
    generation: int | None = None,
) -> list[dict[str, Any]]:
    generation = await usage_cache_generation(generation)
    rows = await cached_day_rows(start, end, account_filter, generation)
    if rows is not None:
        return rows
    report = await usage_facade.usage_report(start, end, account_filter, generation)
    await cache_day_rows_from_report(report, start, end, account_filter, generation)
    return rows_from_report(report, start, end)


async def exchange_rate_for_response() -> dict[str, Any]:
    settings = await store.settings()
    return await fetch_usd_zar(settings, now_local().date())


def days_response(
    start: date,
    end: date,
    rows: list[dict[str, Any]],
    exchange_rate: dict[str, Any],
    hit: bool,
    ttl: int,
    period_from: str | None = None,
    period_to: str | None = None,
) -> dict[str, Any]:
    return {
        "period": {"from": period_from or start.isoformat(), "to": period_to or end.isoformat()},
        "days": rows,
        "weeks": rollup_day_rows(rows, "week"),
        "months": rollup_day_rows(rows, "month"),
        "exchange_rate": exchange_rate,
        "cache": response_cache_meta(hit, ttl),
    }


async def days_report(start: date, end: date, account_filter: set[str] | None = None) -> dict[str, Any]:
    generation = await usage_cache_generation()
    key = versioned_cache_key(generation, days_cache_key(start, end, account_filter))
    ttl = ttl_for_range(start, end)
    cached = await cache.get(key)
    if cached:
        cached = json.loads(json.dumps(cached))
        cached["cache"] = response_cache_meta(True, ttl)
        return cached

    rows = await usage_facade.ensure_daily_cache_for_range(start, end, account_filter, generation)
    result = days_response(start, end, rows, await exchange_rate_for_response(), False, ttl)
    if days_report_has_activity(result):
        await cache.set(key, result, ttl)
    return result


async def days_report_for_window(start_at: datetime, end_at: datetime, account_filter: set[str] | None = None) -> dict[str, Any]:
    generation = await usage_cache_generation()
    key_end_at = cacheable_window_end(start_at, end_at)
    key = versioned_cache_key(generation, days_window_cache_key(start_at, key_end_at, account_filter))
    ttl = ttl_for_window(start_at, end_at)
    cached = await cache.get(key)
    if cached:
        cached = json.loads(json.dumps(cached))
        cached["cache"] = response_cache_meta(True, ttl)
        return cached

    start, end = window_dates(start_at, end_at)
    report = await usage_facade.usage_report_for_window(start_at, key_end_at, account_filter, generation)
    rows = rows_from_report(report, start, end)
    result = days_response(
        start,
        end,
        rows,
        await exchange_rate_for_response(),
        False,
        ttl,
        start_at.isoformat(),
        key_end_at.isoformat(),
    )
    if days_report_has_activity(result):
        await cache.set(key, result, ttl)
    return result


async def materialize_common_ranges(today: date | datetime) -> None:
    with timed_dependency("service.materialize_common_ranges"):
        current_day = today.date() if isinstance(today, datetime) else today
        ranges: set[tuple[date, date]] = set()
        ranges.add((current_day, current_day))
        if current_day > date.min:
            yesterday = current_day - timedelta(days=1)
            ranges.add((yesterday, yesterday))
        ranges.add((week_start(current_day), current_day))
        ranges.add((month_start(current_day), current_day))
        ranges.add(previous_month_bounds(current_day))
        for days_back in MATERIALIZED_DAYS_BACK:
            ranges.add((current_day - timedelta(days=days_back), current_day))

        for start, end in sorted(ranges):
            await usage_facade.usage_report(start, end)
            await usage_facade.ensure_daily_cache_for_range(start, end)
            await usage_facade.days_report(start, end)
            await asyncio.sleep(0)

        local_now = today if isinstance(today, datetime) else now_local()
        tzinfo = local_now.tzinfo
        default_start_at = datetime.combine(current_day - timedelta(days=usage_facade.DEFAULT_DAYS_BACK), time.min, tzinfo)
        default_end_at = datetime.combine(current_day + timedelta(days=1), time.min, tzinfo)
        await usage_facade.usage_report_for_window(default_start_at, default_end_at)
        await usage_facade.days_report_for_window(default_start_at, default_end_at)
        await usage_facade.session_history_report_for_window(default_start_at, default_end_at)
        await asyncio.sleep(0)

        for limit in await store.account_limits(enabled_only=True):
            tz_name = str(limit.get("timezone") or DEFAULT_TZ)
            local_now = resolve_window_reference_time(today, tz_name)
            start_at, end_at = reset_window_for_datetime(
                local_now,
                int(limit.get("reset_weekday", 4)),
                str(limit.get("reset_time") or "00:00"),
            )
            account_filter = {str(limit["account"])}
            await usage_facade.usage_report_for_window(start_at, min(end_at, local_now), account_filter)
            await usage_facade.days_report_for_window(start_at, min(end_at, local_now), account_filter)
            await asyncio.sleep(0)
