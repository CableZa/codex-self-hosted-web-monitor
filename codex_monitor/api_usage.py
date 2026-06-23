from __future__ import annotations

import asyncio
import json
import os
from datetime import date, datetime, time, timedelta, timezone
from pathlib import Path
from time import perf_counter
from typing import Any, Callable
from zoneinfo import ZoneInfo

import codex_usage
from codex_usage_models import ParseDiagnostics
import httpx

from .api_accounts import account_label, account_resolver_from_snapshots, codex_auth_warning, parse_snapshot_time
from .api_cache_keys import (
    day_cache_key,
    days_cache_key,
    days_window_cache_key,
    bucket_window_end_for_cache,
    report_cache_key,
    report_window_cache_key,
    response_cache_meta,
    session_detail_cache_key,
    session_detail_window_cache_key,
    session_history_cache_key,
    session_history_window_cache_key,
    ttl_for_day,
    ttl_for_range,
    ttl_for_window,
    versioned_cache_key,
    window_includes_today,
)
from .api_dates import DEFAULT_TZ, float_setting, iter_days, month_start, now_local, previous_month_bounds, week_start
from .api_limits import reset_window_for_datetime, resolve_window_reference_time
from .api_refs import active_http_client, cache, inflight_session_reports, inflight_usage_reports, store
from .api_timing import logger, timed_dependency
from .session_signals import SessionSignalThresholds, session_signal_thresholds

DEFAULT_DAYS_BACK = int(os.environ.get("DEFAULT_DAYS_BACK", "30"))
MATERIALIZED_DAYS_BACK = (7, 30, 60, 90)
FX_FALLBACK_RETRY_SECONDS = int(os.environ.get("FX_FALLBACK_RETRY_SECONDS", "3600"))
FX_LIVE_ENABLED = os.environ.get("FX_LIVE_ENABLED", "").strip().lower() in {"1", "true", "yes", "on"}
SCANNER_ENABLED = os.environ.get("SCANNER_ENABLED", "").strip().lower() in {"1", "true", "yes", "on"}
USAGE_AGGREGATE_CACHE_SCHEMA = "v4"
USAGE_CACHE_GENERATION_KEY = "usage_cache_generation"
ZERO_ACTIVITY_WINDOW_CACHE_TTL_SECONDS = int(os.environ.get("ZERO_ACTIVITY_WINDOW_CACHE_TTL_SECONDS", "30"))


async def usage_cache_generation(generation: int | None = None) -> int:
    if generation is not None:
        return generation
    return await store.setting_generation(USAGE_CACHE_GENERATION_KEY)


def cacheable_window_end(start_at: datetime, end_at: datetime) -> datetime:
    if window_includes_today(start_at, end_at):
        bucketed = bucket_window_end_for_cache(end_at)
        if bucketed > start_at:
            return bucketed
    return end_at


async def fetch_usd_zar(settings: dict[str, str], day: date) -> dict[str, Any]:
    fallback = float_setting(settings, "usd_zar_fallback_rate", 18.5)
    if not FX_LIVE_ENABLED:
        return {"rate": fallback, "source": "disabled", "day": day.isoformat()}

    cached = await store.get_fx_rate(day)
    if cached:
        source = str(cached["source"])
        fetched_at = parse_snapshot_time(str(cached["fetched_at"]))
        age_seconds = (datetime.now(timezone.utc) - fetched_at).total_seconds()
        if source != "fallback" or age_seconds < FX_FALLBACK_RETRY_SECONDS:
            return {"rate": float(cached["usd_zar"]), "source": source, "day": day.isoformat()}

    url = "https://open.er-api.com/v6/latest/USD"
    try:
        with timed_dependency("api.fx_rate", day=day.isoformat()):
            response = await active_http_client().get(url, timeout=5)
            response.raise_for_status()
            data = response.json()
        rate = float(data["rates"]["ZAR"])
        await store.save_fx_rate(day, rate, "open.er-api.com")
        return {"rate": rate, "source": "open.er-api.com", "day": day.isoformat()}
    except (httpx.HTTPError, TimeoutError, KeyError, ValueError, json.JSONDecodeError) as exc:
        logger.warning("fx_rate_fallback day=%s reason=%s", day.isoformat(), exc)
        await store.save_fx_rate(day, fallback, "fallback")
        return {"rate": fallback, "source": "fallback", "day": day.isoformat()}


def _apply_total_zar(value: Any, usd_zar: float) -> None:
    if isinstance(value, dict):
        if "total_usd" in value:
            value["total_zar"] = round(float(value.get("total_usd", 0)) * usd_zar, 2)
        for nested in value.values():
            _apply_total_zar(nested, usd_zar)
    elif isinstance(value, list):
        for item in value:
            _apply_total_zar(item, usd_zar)


def add_zar(report: dict[str, Any], usd_zar: float) -> dict[str, Any]:
    report = json.loads(json.dumps(report))
    _apply_total_zar(report, usd_zar)
    report["currency"] = {"code": "ZAR", "usd_zar": usd_zar}
    return report


USAGE_METRIC_FIELDS = (
    "input_tokens",
    "cached_input_tokens",
    "output_tokens",
    "reasoning_output_tokens",
    "total_tokens",
    "input_usd",
    "cached_input_usd",
    "output_usd",
    "reasoning_output_usd",
    "total_usd",
    "input_credits",
    "cached_input_credits",
    "output_credits",
    "reasoning_output_credits",
    "total_credits",
)

ACTIVITY_FIELDS = (
    "input_tokens",
    "cached_input_tokens",
    "output_tokens",
    "reasoning_output_tokens",
    "total_tokens",
    "events",
)

_logged_missing_session_roots: set[str] = set()
_logged_no_usage_files: set[str] = set()
_pruned_usage_aggregate_schemas: set[str] = set()


def row_has_usage_activity(row: dict[str, Any]) -> bool:
    return any(float(row.get(field) or 0) > 0 for field in ACTIVITY_FIELDS)


def usage_report_has_activity(report: dict[str, Any]) -> bool:
    totals = report.get("totals")
    if isinstance(totals, dict) and row_has_usage_activity(totals):
        return True
    return any(row_has_usage_activity(row) for row in report.get("by_day", []) if isinstance(row, dict))


def session_report_has_activity(report: dict[str, Any]) -> bool:
    totals = report.get("totals")
    if isinstance(totals, dict) and row_has_usage_activity(totals):
        return True
    sessions = report.get("sessions")
    if isinstance(sessions, list):
        return any(row_has_usage_activity(row) for row in sessions if isinstance(row, dict))
    return row_has_usage_activity(report)


def days_report_has_activity(report: dict[str, Any]) -> bool:
    return any(row_has_usage_activity(row) for row in report.get("days", []) if isinstance(row, dict))


def snapshot_has_usage_activity(snapshot: dict[str, Any]) -> bool:
    reports = snapshot.get("reports")
    if not isinstance(reports, dict):
        return False
    return any(usage_report_has_activity(report) for report in reports.values() if isinstance(report, dict))


def session_discovery_warnings(roots: list[Path], files: list[Path]) -> list[str]:
    existing_roots = [root for root in roots if root.expanduser().exists()]
    warnings: list[str] = []
    if not existing_roots:
        key = "|".join(str(root.expanduser()) for root in roots)
        message = f"Codex usage directories were not found: {', '.join(str(root.expanduser()) for root in roots)}."
        warnings.append(message)
        if key not in _logged_missing_session_roots:
            logger.warning("codex_usage_roots_missing roots=%s", ",".join(str(root.expanduser()) for root in roots))
            _logged_missing_session_roots.add(key)
        return warnings

    if not files:
        key = "|".join(str(root.expanduser()) for root in existing_roots)
        message = f"No Codex usage files were found under: {', '.join(str(root.expanduser()) for root in existing_roots)}."
        warnings.append(message)
        if key not in _logged_no_usage_files:
            logger.warning("codex_usage_files_missing roots=%s pattern=rollout-*.jsonl", ",".join(str(root.expanduser()) for root in existing_roots))
            _logged_no_usage_files.add(key)
    return warnings


def usage_aggregate_cache_version(prices: dict[str, Any], unknown_account_mapping: str = "") -> str:
    return ":".join(
        [
            USAGE_AGGREGATE_CACHE_SCHEMA,
            str(prices.get("updated") or "unknown"),
            str(prices.get("credit_source") or "unknown"),
            f"unknown={unknown_account_mapping or 'unknown'}",
        ]
    )


def empty_usage_bucket() -> dict[str, Any]:
    return {
        **{field: 0 for field in USAGE_METRIC_FIELDS},
        "long_context_applied": False,
        "long_context_events": 0,
        "max_input_tokens": 0,
        "events": 0,
        "sessions": set(),
        "files": set(),
    }


def row_set(row: dict[str, Any], key: str) -> set[str]:
    value = row.get(key)
    if isinstance(value, set):
        return value
    if isinstance(value, list):
        return {str(item) for item in value}
    if isinstance(value, str):
        try:
            return {str(item) for item in json.loads(value)}
        except json.JSONDecodeError:
            return set()
    return set()


def add_aggregate_row(bucket: dict[str, Any], row: dict[str, Any]) -> None:
    for field in USAGE_METRIC_FIELDS:
        bucket[field] += row.get(field, 0) or 0
    bucket["long_context_applied"] = bucket["long_context_applied"] or bool(row.get("long_context_applied"))
    bucket["long_context_events"] += int(row.get("long_context_events") or (1 if row.get("long_context_applied") else 0))
    bucket["max_input_tokens"] = max(
        int(bucket.get("max_input_tokens") or 0),
        int(row.get("max_input_tokens") or row.get("input_tokens") or 0),
    )
    bucket["events"] += int(row.get("events") or 0)
    bucket["sessions"].update(row_set(row, "sessions"))
    bucket["files"].update(row_set(row, "files"))


def bucket_as_report_row(bucket: dict[str, Any]) -> dict[str, Any]:
    input_tokens = int(bucket["input_tokens"])
    cached_input_tokens = int(bucket["cached_input_tokens"])
    return {
        "input_tokens": input_tokens,
        "cached_input_tokens": cached_input_tokens,
        "uncached_input_tokens": max(
            input_tokens - min(cached_input_tokens, input_tokens),
            0,
        ),
        "output_tokens": int(bucket["output_tokens"]),
        "reasoning_output_tokens": int(bucket["reasoning_output_tokens"]),
        "total_tokens": int(bucket["total_tokens"]),
        "input_usd": round(float(bucket["input_usd"]), 8),
        "cached_input_usd": round(float(bucket["cached_input_usd"]), 8),
        "output_usd": round(float(bucket["output_usd"]), 8),
        "reasoning_output_usd": round(float(bucket["reasoning_output_usd"]), 8),
        "total_usd": round(float(bucket["total_usd"]), 8),
        "input_credits": round(float(bucket["input_credits"]), 8),
        "cached_input_credits": round(float(bucket["cached_input_credits"]), 8),
        "output_credits": round(float(bucket["output_credits"]), 8),
        "reasoning_output_credits": round(float(bucket["reasoning_output_credits"]), 8),
        "total_credits": round(float(bucket["total_credits"]), 8),
        "long_context_applied": bool(bucket["long_context_applied"]),
        "long_context_events": int(bucket.get("long_context_events") or 0),
        "max_input_tokens": int(bucket.get("max_input_tokens") or 0),
        "cache_hit_ratio": round(cached_input_tokens / input_tokens, 4) if input_tokens else 0,
        "events": int(bucket["events"]),
        "sessions": len(bucket["sessions"]),
        "files": len(bucket["files"]),
    }


def app_day_for_record(record: codex_usage.UsageRecord) -> str:
    return record.timestamp.astimezone(ZoneInfo(DEFAULT_TZ)).date().isoformat()


def filter_records_for_app_period(records: list[codex_usage.UsageRecord], start: date, end: date) -> list[codex_usage.UsageRecord]:
    filtered: list[codex_usage.UsageRecord] = []
    for record in records:
        record_day = date.fromisoformat(app_day_for_record(record))
        if record_day < start or record_day > end:
            continue
        filtered.append(record)
    return filtered


def scan_usage_files_for_period_sync(
    start: date,
    end: date,
    start_at: datetime | None = None,
    end_at: datetime | None = None,
    diagnostics: ParseDiagnostics | None = None,
    include_metadata: bool = True,
) -> tuple[list[codex_usage.UsageRecord], dict[str, codex_usage.SessionMetadata], list[Path], list[Path], list[str]]:
    started = perf_counter()
    codex_home = Path(os.environ.get("CODEX_HOME", codex_usage.DEFAULT_CODEX_HOME))
    roots = codex_usage.default_session_roots(codex_home)
    try:
        discovered_files = codex_usage.discover_session_files(roots, diagnostics)
        warnings = session_discovery_warnings(roots, discovered_files)
        auth_warning = codex_auth_warning(codex_home)
        if auth_warning:
            warnings.append(auth_warning)
        files = codex_usage.filter_session_files_by_period(discovered_files, start, end)
        records = filter_records_for_app_period(codex_usage.read_records(files, None, None, start_at, end_at, diagnostics), start, end)
        metadata = codex_usage.read_session_metadata(files, diagnostics) if include_metadata else {}
        return records, metadata, files, roots, sorted(set(warnings))
    finally:
        if diagnostics is not None:
            diagnostics.total_scan_ms += round((perf_counter() - started) * 1000)


def window_dates(start_at: datetime, end_at: datetime) -> tuple[date, date]:
    tz = ZoneInfo(DEFAULT_TZ)
    start = start_at.astimezone(tz).date()
    end = (end_at - timedelta(microseconds=1)).astimezone(tz).date()
    return start, end


def exact_period(start_at: datetime, end_at: datetime) -> dict[str, str]:
    return {"from": start_at.isoformat(), "to": end_at.isoformat()}




async def compute_usage_report(start: date, end: date, account_filter: set[str] | None = None) -> dict[str, Any]:
    settings = await store.settings()
    codex_home = Path(os.environ.get("CODEX_HOME", codex_usage.DEFAULT_CODEX_HOME))
    snapshots = await store.auth_snapshots(limit=1000)
    prices = codex_usage.load_prices(codex_usage.DEFAULT_PRICES_PATH)
    unknown_account_mapping = settings.get("unknown_account_mapping", "")
    cache_version = usage_aggregate_cache_version(prices, unknown_account_mapping)
    roots = codex_usage.default_session_roots(codex_home.expanduser())
    today = now_local().date()
    rows: list[dict[str, Any]] = []
    warnings: list[str] = []
    if start < today:
        historic_end = min(end, today - timedelta(days=1))
        if SCANNER_ENABLED:
            warnings.extend(await ensure_historic_usage_aggregates(cache_version, start, historic_end, snapshots, unknown_account_mapping))
            rows.extend(await store.usage_aggregate_rows(cache_version, start, historic_end, account_filter))
            warnings.extend(await store.usage_aggregate_warnings(cache_version, start, historic_end))
        else:
            with timed_dependency("service.codex_scan_historic", start=start.isoformat(), end=historic_end.isoformat()):
                historic_rows, historic_warnings = await aggregate_rows_for_period(
                    start,
                    historic_end,
                    snapshots,
                    account_filter,
                    unknown_account_mapping=unknown_account_mapping,
                )
            rows.extend(historic_rows)
            warnings.extend(historic_warnings)
    if end >= today:
        live_start = max(start, today)
        with timed_dependency("service.codex_scan", start=live_start.isoformat(), end=end.isoformat()):
            live_rows, live_warnings = await aggregate_rows_for_period(live_start, end, snapshots, account_filter, unknown_account_mapping=unknown_account_mapping)
        rows.extend(live_rows)
        warnings.extend(live_warnings)
    report = report_from_aggregate_rows(rows, prices, start, end, warnings, roots)
    fx = await fetch_usd_zar(settings, now_local().date())
    report = add_zar(report, fx["rate"])
    report["exchange_rate"] = fx
    report["accounts"] = report_account_labels(report, snapshots)
    return report


async def usage_report(
    start: date,
    end: date,
    account_filter: set[str] | None = None,
    generation: int | None = None,
) -> dict[str, Any]:
    generation = await usage_cache_generation(generation)
    key = versioned_cache_key(generation, report_cache_key(start, end, account_filter))
    ttl = ttl_for_range(start, end)
    cached = await cache.get(key)
    if cached:
        cached = json.loads(json.dumps(cached))
        cached["cache"] = response_cache_meta(True, ttl)
        return cached

    task = inflight_usage_reports.get(key)
    if task is None:
        async def build_and_cache() -> dict[str, Any]:
            report = await compute_usage_report(start, end, account_filter)
            report["cache"] = response_cache_meta(False, ttl)
            if usage_report_has_activity(report):
                await cache.set(key, report, ttl)
            return report

        task = asyncio.create_task(build_and_cache())
        inflight_usage_reports[key] = task
    try:
        return await task
    finally:
        if inflight_usage_reports.get(key) is task:
            inflight_usage_reports.pop(key, None)


async def compute_session_history_report(start: date, end: date, account_filter: set[str] | None = None) -> dict[str, Any]:
    settings = await store.settings()
    snapshots = await store.auth_snapshots(limit=1000)
    prices = codex_usage.load_prices(codex_usage.DEFAULT_PRICES_PATH)
    unknown_account_mapping = settings.get("unknown_account_mapping", "")
    thresholds = session_signal_thresholds(settings)
    records, metadata, files, roots, warnings = await asyncio.to_thread(scan_usage_files_for_period_sync, start, end)
    report = session_history_report_from_records(
        records,
        prices,
        metadata,
        len(files),
        roots,
        start,
        end,
        warnings,
        account_resolver_from_snapshots(snapshots, unknown_account_mapping),
        account_filter,
        snapshots,
        thresholds=thresholds,
    )
    fx = await fetch_usd_zar(settings, now_local().date())
    report = add_zar(report, fx["rate"])
    report["exchange_rate"] = fx
    report["accounts"] = report_account_labels(report, snapshots)
    return report


async def compute_session_history_report_for_window(start_at: datetime, end_at: datetime, account_filter: set[str] | None = None) -> dict[str, Any]:
    settings = await store.settings()
    snapshots = await store.auth_snapshots(limit=1000)
    prices = codex_usage.load_prices(codex_usage.DEFAULT_PRICES_PATH)
    unknown_account_mapping = settings.get("unknown_account_mapping", "")
    thresholds = session_signal_thresholds(settings)
    start, end = window_dates(start_at, end_at)
    records, metadata, files, roots, warnings = await asyncio.to_thread(scan_usage_files_for_period_sync, start, end, start_at, end_at)
    report = session_history_report_from_records(
        records,
        prices,
        metadata,
        len(files),
        roots,
        start,
        end,
        warnings,
        account_resolver_from_snapshots(snapshots, unknown_account_mapping),
        account_filter,
        snapshots,
        start_at,
        end_at,
        thresholds=thresholds,
    )
    fx = await fetch_usd_zar(settings, now_local().date())
    report = add_zar(report, fx["rate"])
    report["exchange_rate"] = fx
    report["accounts"] = report_account_labels(report, snapshots)
    return report


async def compute_session_detail_report(
    start: date,
    end: date,
    session_id: str,
    account_filter: set[str] | None = None,
) -> dict[str, Any] | None:
    settings = await store.settings()
    snapshots = await store.auth_snapshots(limit=1000)
    prices = codex_usage.load_prices(codex_usage.DEFAULT_PRICES_PATH)
    unknown_account_mapping = settings.get("unknown_account_mapping", "")
    thresholds = session_signal_thresholds(settings)
    records, metadata, files, roots, warnings = await asyncio.to_thread(scan_usage_files_for_period_sync, start, end)
    report = session_detail_report_from_records(
        records,
        prices,
        metadata,
        len(files),
        roots,
        start,
        end,
        warnings,
        session_id,
        account_resolver_from_snapshots(snapshots, unknown_account_mapping),
        account_filter,
        thresholds=thresholds,
    )
    if report is None:
        return None
    fx = await fetch_usd_zar(settings, now_local().date())
    report = add_zar(report, fx["rate"])
    report["exchange_rate"] = fx
    return report


async def compute_session_detail_report_for_window(
    start_at: datetime,
    end_at: datetime,
    session_id: str,
    account_filter: set[str] | None = None,
) -> dict[str, Any] | None:
    settings = await store.settings()
    snapshots = await store.auth_snapshots(limit=1000)
    prices = codex_usage.load_prices(codex_usage.DEFAULT_PRICES_PATH)
    unknown_account_mapping = settings.get("unknown_account_mapping", "")
    thresholds = session_signal_thresholds(settings)
    start, end = window_dates(start_at, end_at)
    records, metadata, files, roots, warnings = await asyncio.to_thread(scan_usage_files_for_period_sync, start, end, start_at, end_at)
    report = session_detail_report_from_records(
        records,
        prices,
        metadata,
        len(files),
        roots,
        start,
        end,
        warnings,
        session_id,
        account_resolver_from_snapshots(snapshots, unknown_account_mapping),
        account_filter,
        start_at,
        end_at,
        thresholds=thresholds,
    )
    if report is None:
        return None
    fx = await fetch_usd_zar(settings, now_local().date())
    report = add_zar(report, fx["rate"])
    report["exchange_rate"] = fx
    return report


async def session_history_report(start: date, end: date, account_filter: set[str] | None = None) -> dict[str, Any]:
    generation = await usage_cache_generation()
    key = versioned_cache_key(generation, session_history_cache_key(start, end, account_filter))
    ttl = ttl_for_range(start, end)
    cached = await cache.get(key)
    if cached:
        cached = json.loads(json.dumps(cached))
        cached["cache"] = response_cache_meta(True, ttl)
        return cached

    task = inflight_session_reports.get(key)
    if task is None:
        async def build_and_cache() -> dict[str, Any]:
            report = await compute_session_history_report(start, end, account_filter)
            report["cache"] = response_cache_meta(False, ttl)
            if session_report_has_activity(report):
                await cache.set(key, report, ttl)
            return report

        task = asyncio.create_task(build_and_cache())
        inflight_session_reports[key] = task
    try:
        return await task
    finally:
        if inflight_session_reports.get(key) is task:
            inflight_session_reports.pop(key, None)


async def session_history_report_for_window(start_at: datetime, end_at: datetime, account_filter: set[str] | None = None) -> dict[str, Any]:
    generation = await usage_cache_generation()
    key_end_at = cacheable_window_end(start_at, end_at)
    key = versioned_cache_key(generation, session_history_window_cache_key(start_at, key_end_at, account_filter))
    ttl = ttl_for_window(start_at, end_at)
    cached = await cache.get(key)
    if cached:
        cached = json.loads(json.dumps(cached))
        cached["cache"] = response_cache_meta(True, ttl)
        return cached

    task = inflight_session_reports.get(key)
    if task is None:
        async def build_and_cache() -> dict[str, Any]:
            report = await compute_session_history_report_for_window(start_at, key_end_at, account_filter)
            report["cache"] = response_cache_meta(False, ttl)
            if session_report_has_activity(report):
                await cache.set(key, report, ttl)
            return report

        task = asyncio.create_task(build_and_cache())
        inflight_session_reports[key] = task
    try:
        return await task
    finally:
        if inflight_session_reports.get(key) is task:
            inflight_session_reports.pop(key, None)


async def session_detail_report(
    start: date,
    end: date,
    session_id: str,
    account_filter: set[str] | None = None,
) -> dict[str, Any] | None:
    generation = await usage_cache_generation()
    key = versioned_cache_key(generation, session_detail_cache_key(session_id, start, end, account_filter))
    ttl = ttl_for_range(start, end)
    cached = await cache.get(key)
    if cached:
        cached = json.loads(json.dumps(cached))
        cached["cache"] = response_cache_meta(True, ttl)
        return cached

    task = inflight_session_reports.get(key)
    if task is None:
        async def build_and_cache() -> dict[str, Any] | None:
            report = await compute_session_detail_report(start, end, session_id, account_filter)
            if report is None:
                return None
            report["cache"] = response_cache_meta(False, ttl)
            if session_report_has_activity(report):
                await cache.set(key, report, ttl)
            return report

        task = asyncio.create_task(build_and_cache())
        inflight_session_reports[key] = task
    try:
        return await task
    finally:
        if inflight_session_reports.get(key) is task:
            inflight_session_reports.pop(key, None)


async def session_detail_report_for_window(
    start_at: datetime,
    end_at: datetime,
    session_id: str,
    account_filter: set[str] | None = None,
) -> dict[str, Any] | None:
    generation = await usage_cache_generation()
    key_end_at = cacheable_window_end(start_at, end_at)
    key = versioned_cache_key(generation, session_detail_window_cache_key(session_id, start_at, key_end_at, account_filter))
    ttl = ttl_for_window(start_at, end_at)
    cached = await cache.get(key)
    if cached:
        cached = json.loads(json.dumps(cached))
        cached["cache"] = response_cache_meta(True, ttl)
        return cached

    task = inflight_session_reports.get(key)
    if task is None:
        async def build_and_cache() -> dict[str, Any] | None:
            report = await compute_session_detail_report_for_window(start_at, key_end_at, session_id, account_filter)
            if report is None:
                return None
            report["cache"] = response_cache_meta(False, ttl)
            if session_report_has_activity(report):
                await cache.set(key, report, ttl)
            return report

        task = asyncio.create_task(build_and_cache())
        inflight_session_reports[key] = task
    try:
        return await task
    finally:
        if inflight_session_reports.get(key) is task:
            inflight_session_reports.pop(key, None)


async def compute_usage_report_for_window(start_at: datetime, end_at: datetime, account_filter: set[str] | None = None) -> dict[str, Any]:
    settings = await store.settings()
    codex_home = Path(os.environ.get("CODEX_HOME", codex_usage.DEFAULT_CODEX_HOME))
    snapshots = await store.auth_snapshots(limit=1000)
    prices = codex_usage.load_prices(codex_usage.DEFAULT_PRICES_PATH)
    unknown_account_mapping = settings.get("unknown_account_mapping", "")
    cache_version = usage_aggregate_cache_version(prices, unknown_account_mapping)
    roots = codex_usage.default_session_roots(codex_home.expanduser())
    start, end = window_dates(start_at, end_at)
    today = now_local().date()
    local_tz = ZoneInfo(DEFAULT_TZ)
    local_start_at = start_at.astimezone(local_tz)
    local_end_at = end_at.astimezone(local_tz)
    full_completed_days: list[date] = []
    boundary_or_missing_days: list[date] = []
    for day in iter_days(start, end):
        day_start = datetime.combine(day, time.min, local_tz)
        day_end = day_start + timedelta(days=1)
        if day < today and day_start >= local_start_at and day_end <= local_end_at:
            full_completed_days.append(day)
        else:
            boundary_or_missing_days.append(day)

    rows: list[dict[str, Any]] = []
    warnings: list[str] = []
    present_full_days: set[str] = set()
    if full_completed_days:
        full_start = min(full_completed_days)
        full_end = max(full_completed_days)
        present_full_days = await store.usage_aggregate_days(cache_version, full_start, full_end)
        aggregate_days = [day for day in full_completed_days if day.isoformat() in present_full_days]
        if aggregate_days:
            aggregate_start = min(aggregate_days)
            aggregate_end = max(aggregate_days)
            rows.extend(await store.usage_aggregate_rows(cache_version, aggregate_start, aggregate_end, account_filter))
            warnings.extend(await store.usage_aggregate_warnings(cache_version, aggregate_start, aggregate_end))

    scan_days = boundary_or_missing_days + [day for day in full_completed_days if day.isoformat() not in present_full_days]
    for day in sorted(set(scan_days)):
        is_missing_full_day = day in full_completed_days and day.isoformat() not in present_full_days
        day_start = datetime.combine(day, time.min, local_tz)
        day_end = day_start + timedelta(days=1)
        clipped_start_at = max(local_start_at, day_start)
        clipped_end_at = min(local_end_at, day_end)
        if clipped_start_at >= clipped_end_at:
            continue
        with timed_dependency(
            "service.codex_scan_window_day",
            day=day.isoformat(),
            start_at=clipped_start_at.isoformat(),
            end_at=clipped_end_at.isoformat(),
        ):
            day_rows, day_warnings = await aggregate_rows_for_period(
                day,
                day,
                snapshots,
                account_filter,
                clipped_start_at,
                clipped_end_at,
                unknown_account_mapping,
            )
        rows.extend(day_rows)
        warnings.extend(day_warnings)
        if is_missing_full_day and account_filter is None:
            await store.save_usage_daily_aggregate(cache_version, day, day_rows, day_warnings)
    report = report_from_aggregate_rows(rows, prices, start, end, warnings, roots)
    report["period"] = exact_period(start_at, end_at)
    fx = await fetch_usd_zar(settings, now_local().date())
    report = add_zar(report, fx["rate"])
    report["exchange_rate"] = fx
    report["accounts"] = report_account_labels(report, snapshots)
    return report


async def usage_report_for_window(
    start_at: datetime,
    end_at: datetime,
    account_filter: set[str] | None = None,
    generation: int | None = None,
) -> dict[str, Any]:
    generation = await usage_cache_generation(generation)
    key_end_at = cacheable_window_end(start_at, end_at)
    key = versioned_cache_key(generation, report_window_cache_key(start_at, key_end_at, account_filter))
    ttl = ttl_for_window(start_at, end_at)
    cached = await cache.get(key)
    if cached:
        cached = json.loads(json.dumps(cached))
        cached["cache"] = response_cache_meta(True, ttl)
        return cached

    task = inflight_usage_reports.get(key)
    if task is None:
        async def build_and_cache() -> dict[str, Any]:
            report = await compute_usage_report_for_window(start_at, key_end_at, account_filter)
            report["cache"] = response_cache_meta(False, ttl)
            if usage_report_has_activity(report):
                await cache.set(key, report, ttl)
            elif window_includes_today(start_at, key_end_at):
                await cache.set(key, report, ZERO_ACTIVITY_WINDOW_CACHE_TTL_SECONDS)
            return report

        task = asyncio.create_task(build_and_cache())
        inflight_usage_reports[key] = task
    try:
        return await task
    finally:
        if inflight_usage_reports.get(key) is task:
            inflight_usage_reports.pop(key, None)


from .api_usage_aggregates import aggregate_rows_for_period, aggregate_rows_for_period_sync, aggregate_rows_from_records
from .api_usage_aggregates import ensure_historic_usage_aggregates, report_account_labels, report_from_aggregate_rows
from .api_usage_days import cache_day_rows_from_report, cached_day_rows, day_row_from_report, days_report
from .api_usage_days import days_report_for_window, days_response, empty_day_row, ensure_daily_cache_for_range
from .api_usage_days import exchange_rate_for_response, materialize_common_ranges, rows_from_report
from .api_usage_sessions import account_switches_from_snapshots, aggregate_session_buckets_from_records, apply_session_metadata
from .api_usage_sessions import cache_efficiency, cache_report_from_sessions, empty_session_bucket, long_context_reasons
from .api_usage_sessions import project_rows_from_sessions, session_detail_from_bucket, session_detail_report_from_records
from .api_usage_sessions import session_history_report_from_records, session_model_rows_from_bucket, session_summary_from_bucket
from .api_usage_sessions import session_summary_text, utc_iso
