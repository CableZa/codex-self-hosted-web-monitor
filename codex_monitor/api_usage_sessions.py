from __future__ import annotations

from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Callable
from zoneinfo import ZoneInfo

import codex_usage

from .usage_waste import add_waste_fields
from .api_usage import (
    DEFAULT_TZ,
    SessionSignalThresholds,
    account_label,
    add_aggregate_row,
    app_day_for_record,
    bucket_as_report_row,
    empty_usage_bucket,
    exact_period,
    parse_snapshot_time,
    session_signal_thresholds,
)


def empty_session_bucket(session_id: str) -> dict[str, Any]:
    return {
        **empty_usage_bucket(),
        "session_id": session_id,
        "first_seen": None,
        "last_seen": None,
        "accounts": set(),
        "efforts": set(),
        "models": {},
        "timeline": [],
        "first_message": None,
        "last_message": None,
        "project_path": None,
        "project_name": None,
    }


def utc_iso(timestamp: datetime) -> str:
    return timestamp.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")


def add_session_record(bucket: dict[str, Any], record: codex_usage.UsageRecord, account: str, priced_model: str, cost: codex_usage.CostBreakdown) -> None:
    metric_row = {
        **record.usage.as_dict(),
        **cost.as_dict(),
        "events": 1,
        "sessions": {record.session_id},
        "files": {record.path},
        "long_context_events": 1 if cost.long_context_applied else 0,
        "max_input_tokens": record.usage.input_tokens,
    }
    add_aggregate_row(bucket, metric_row)
    event_timestamp = record.timestamp.astimezone(timezone.utc)
    first_seen = bucket["first_seen"]
    last_seen = bucket["last_seen"]
    if first_seen is None or event_timestamp < first_seen:
        bucket["first_seen"] = event_timestamp
    if last_seen is None or event_timestamp > last_seen:
        bucket["last_seen"] = event_timestamp
    bucket["accounts"].add(account)
    bucket["efforts"].add(record.effort)
    model_bucket = bucket["models"].setdefault(priced_model, {**empty_usage_bucket(), "model": priced_model})
    add_aggregate_row(model_bucket, metric_row)
    bucket["timeline"].append(
        {
            "timestamp": utc_iso(event_timestamp),
            "day": app_day_for_record(record),
            "model": record.model,
            "priced_model": priced_model,
            "effort": record.effort,
            "account": account,
            "path": record.path,
            "long_context_events": 1 if cost.long_context_applied else 0,
            "max_input_tokens": record.usage.input_tokens,
            **record.usage.as_dict(),
            **cost.as_dict(),
        }
    )


def session_model_rows_from_bucket(bucket: dict[str, Any]) -> list[dict[str, Any]]:
    return [
        {"model": model, **bucket_as_report_row(model_bucket)}
        for model, model_bucket in sorted(bucket["models"].items(), key=lambda item: item[1]["total_credits"], reverse=True)
    ]


def apply_session_metadata(bucket: dict[str, Any], metadata: codex_usage.SessionMetadata | None) -> None:
    if metadata is None:
        return
    bucket["first_message"] = metadata.first_message
    bucket["last_message"] = metadata.last_message
    bucket["project_path"] = metadata.project_path
    bucket["project_name"] = metadata.project_name
    bucket["user_message_count"] = metadata.user_message_count
    bucket["first_message_word_count"] = metadata.first_message_word_count
    bucket["tool_call_count"] = metadata.tool_call_count
    bucket["tool_error_count"] = metadata.tool_error_count
    bucket["max_consecutive_tool_errors"] = metadata.max_consecutive_tool_errors
    bucket["repeated_tool_signatures"] = metadata.repeated_tool_signatures
    bucket["web_tool_call_count"] = metadata.web_tool_call_count
    bucket["large_ingest_count"] = metadata.large_ingest_count


def cache_efficiency(bucket: dict[str, Any]) -> float:
    input_tokens = int(bucket.get("input_tokens") or 0)
    if input_tokens <= 0:
        return 0
    cached_tokens = min(int(bucket.get("cached_input_tokens") or 0), input_tokens)
    return round(cached_tokens / input_tokens, 4)


def long_context_reasons(bucket: dict[str, Any], thresholds: SessionSignalThresholds | None = None) -> list[str]:
    active_thresholds = thresholds or session_signal_thresholds()
    reasons: list[str] = []
    input_tokens = int(bucket.get("input_tokens") or 0)
    uncached_tokens = max(input_tokens - min(int(bucket.get("cached_input_tokens") or 0), input_tokens), 0)
    output_tokens = int(bucket.get("output_tokens") or 0)
    total_tokens = int(bucket.get("total_tokens") or 0)
    cache_reuse = 1 - (uncached_tokens / input_tokens) if input_tokens else 0
    if input_tokens >= active_thresholds.high_input_tokens:
        reasons.append("high input volume")
    if uncached_tokens >= active_thresholds.high_uncached_input_tokens:
        reasons.append("high uncached input")
    if input_tokens and uncached_tokens >= active_thresholds.low_cache_min_uncached_tokens and cache_reuse <= active_thresholds.low_cache_max_reuse_ratio:
        reasons.append("low cache reuse")
    if total_tokens >= active_thresholds.large_total_tokens:
        reasons.append("large token footprint")
    if output_tokens >= active_thresholds.high_output_tokens:
        reasons.append("high output volume")
    if active_thresholds.long_context_pricing_signal_enabled and bucket.get("long_context_applied"):
        reasons.append("long-context pricing")
    return reasons


def session_summary_text(bucket: dict[str, Any]) -> str:
    project = bucket.get("project_name") or "unknown project"
    models = ", ".join(sorted(bucket.get("models", {}).keys())) or "unknown model"
    accounts = ", ".join(sorted(bucket.get("accounts", set()))) or "unknown account"
    credits = round(float(bucket.get("total_credits") or 0), 1)
    cache_percent = round(cache_efficiency(bucket) * 100)
    return f"{project} used {credits:g} credits on {models} for {accounts}, with {cache_percent}% input cache reuse."


def session_summary_from_bucket(bucket: dict[str, Any], thresholds: SessionSignalThresholds | None = None) -> dict[str, Any]:
    first_seen = bucket["first_seen"]
    last_seen = bucket["last_seen"]
    duration_seconds = 0
    if isinstance(first_seen, datetime) and isinstance(last_seen, datetime):
        duration_seconds = max(int((last_seen - first_seen).total_seconds()), 0)
    summary = {
        "session_id": bucket["session_id"],
        "first_seen": utc_iso(first_seen) if isinstance(first_seen, datetime) else None,
        "last_seen": utc_iso(last_seen) if isinstance(last_seen, datetime) else None,
        "duration_seconds": duration_seconds,
        "first_message": bucket.get("first_message"),
        "last_message": bucket.get("last_message"),
        "display_title": bucket.get("first_message") or bucket["session_id"],
        "project_path": bucket.get("project_path"),
        "project_name": bucket.get("project_name"),
        "cache_efficiency": cache_efficiency(bucket),
        "long_context": bool(long_context_reasons(bucket, thresholds)),
        "long_context_reasons": long_context_reasons(bucket, thresholds),
        "summary": session_summary_text(bucket),
        "accounts": sorted(bucket["accounts"]),
        "efforts": sorted(bucket.get("efforts", set())),
        "user_message_count": int(bucket.get("user_message_count") or 0),
        "first_message_word_count": int(bucket.get("first_message_word_count") or 0),
        "tool_call_count": int(bucket.get("tool_call_count") or 0),
        "tool_error_count": int(bucket.get("tool_error_count") or 0),
        "max_consecutive_tool_errors": int(bucket.get("max_consecutive_tool_errors") or 0),
        "repeated_tool_signatures": int(bucket.get("repeated_tool_signatures") or 0),
        "web_tool_call_count": int(bucket.get("web_tool_call_count") or 0),
        "large_ingest_count": int(bucket.get("large_ingest_count") or 0),
        "by_model": session_model_rows_from_bucket(bucket),
        **bucket_as_report_row(bucket),
    }
    return add_waste_fields(summary, thresholds)


def session_detail_from_bucket(bucket: dict[str, Any], thresholds: SessionSignalThresholds | None = None) -> dict[str, Any]:
    return {
        **session_summary_from_bucket(bucket, thresholds),
        "timeline": sorted(bucket["timeline"], key=lambda item: item["timestamp"]),
    }


def aggregate_session_buckets_from_records(
    records: list[codex_usage.UsageRecord],
    prices: dict[str, Any],
    metadata: dict[str, codex_usage.SessionMetadata] | None = None,
    account_resolver: Callable[[codex_usage.UsageRecord], str] | None = None,
    account_filter: set[str] | None = None,
    session_id_filter: str | None = None,
) -> tuple[dict[str, dict[str, Any]], list[str]]:
    buckets: dict[str, dict[str, Any]] = {}
    warnings: set[str] = set()
    for record in records:
        if session_id_filter and record.session_id != session_id_filter:
            continue
        account = account_resolver(record) if account_resolver else record.account
        account = account or "unknown"
        if account_filter and account not in account_filter:
            continue
        priced_model, rates = codex_usage.lookup_rates(record.model, prices)
        model_key = priced_model or record.model
        if rates is None:
            warnings.add(f"No price found for model '{record.model}'. Cost for those events is $0.")
            cost = codex_usage.CostBreakdown()
        else:
            cost = codex_usage.cost_for_usage(record.usage, rates)
            if priced_model != record.model:
                warnings.add(f"Model '{record.model}' priced as '{priced_model}'.")
        bucket = buckets.setdefault(record.session_id, empty_session_bucket(record.session_id))
        add_session_record(bucket, record, account, model_key, cost)
    for session_id, bucket in buckets.items():
        apply_session_metadata(bucket, (metadata or {}).get(session_id))
    return buckets, sorted(warnings)


def project_rows_from_sessions(sessions: list[dict[str, Any]]) -> list[dict[str, Any]]:
    projects: dict[tuple[str, str], dict[str, Any]] = {}
    for session in sessions:
        project_name = str(session.get("project_name") or "Unknown project")
        project_path = str(session.get("project_path") or "")
        bucket = projects.setdefault((project_name, project_path), {**empty_usage_bucket(), "project_name": project_name, "project_path": project_path})
        file_count = int(session.get("files") or 0)
        file_keys = {f"{session['session_id']}:{index}" for index in range(file_count)}
        add_aggregate_row(bucket, {**session, "sessions": {str(session["session_id"])}, "files": file_keys})
    return sorted(
        [
            {
                "project": project_name,
                "project_path": project_path or None,
                **bucket_as_report_row(bucket),
            }
            for (project_name, project_path), bucket in projects.items()
        ],
        key=lambda item: item["total_credits"],
        reverse=True,
    )


def cache_report_from_sessions(
    sessions: list[dict[str, Any]],
    overall: dict[str, Any],
    thresholds: SessionSignalThresholds | None = None,
) -> dict[str, Any]:
    active_thresholds = thresholds or session_signal_thresholds()
    inefficient = [
        session
        for session in sessions
        if int(session.get("uncached_input_tokens") or 0) >= active_thresholds.low_cache_min_uncached_tokens
        and float(session.get("cache_efficiency") or 0) <= active_thresholds.low_cache_max_reuse_ratio
    ]
    return {
        "cache_efficiency": cache_efficiency(overall),
        "cached_input_tokens": int(overall.get("cached_input_tokens") or 0),
        "uncached_input_tokens": max(
            int(overall.get("input_tokens") or 0) - min(int(overall.get("cached_input_tokens") or 0), int(overall.get("input_tokens") or 0)),
            0,
        ),
        "inefficient_sessions": len(inefficient),
    }


def account_switches_from_snapshots(
    snapshots: list[dict[str, Any]],
    start_day: date,
    end_day: date,
    start_at: datetime | None = None,
    end_at: datetime | None = None,
) -> list[dict[str, Any]]:
    app_tz = ZoneInfo(DEFAULT_TZ)
    window_start = start_at or datetime.combine(start_day, datetime.min.time(), app_tz)
    window_end = end_at or datetime.combine(end_day + timedelta(days=1), datetime.min.time(), app_tz)
    switches: list[dict[str, Any]] = []
    previous: str | None = None
    for snapshot in sorted((item for item in snapshots if item.get("observed_at")), key=lambda item: parse_snapshot_time(str(item["observed_at"]))):
        observed_at = parse_snapshot_time(str(snapshot["observed_at"]))
        label = account_label(snapshot)
        if label == previous:
            continue
        if previous is not None and window_start <= observed_at < window_end:
            switches.append(
                {
                    "observed_at": utc_iso(observed_at),
                    "from_account": previous,
                    "to_account": label,
                    "source": snapshot.get("source"),
                }
            )
        previous = label
    return switches


def session_history_report_from_records(
    records: list[codex_usage.UsageRecord],
    prices: dict[str, Any],
    metadata: dict[str, codex_usage.SessionMetadata],
    files_scanned: int,
    roots: list[Path],
    start_day: date,
    end_day: date,
    warnings: list[str],
    account_resolver: Callable[[codex_usage.UsageRecord], str] | None = None,
    account_filter: set[str] | None = None,
    snapshots: list[dict[str, Any]] | None = None,
    start_at: datetime | None = None,
    end_at: datetime | None = None,
    thresholds: SessionSignalThresholds | None = None,
) -> dict[str, Any]:
    active_thresholds = thresholds or session_signal_thresholds()
    buckets, session_warnings = aggregate_session_buckets_from_records(records, prices, metadata, account_resolver, account_filter)
    overall = empty_usage_bucket()
    sessions = []
    for bucket in buckets.values():
        add_aggregate_row(overall, bucket)
        sessions.append(session_summary_from_bucket(bucket, active_thresholds))
    sessions.sort(key=lambda item: ((item.get("last_seen") or ""), (item.get("first_seen") or ""), item["session_id"]), reverse=True)
    return {
        "generated_at": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        "period": exact_period(start_at, end_at) if start_at and end_at else {"from": start_day.isoformat(), "to": end_day.isoformat()},
        "source_roots": [str(root.expanduser()) for root in roots],
        "files_scanned": files_scanned,
        "usage_events": int(overall["events"]),
        "totals": bucket_as_report_row(overall),
        "sessions": sessions,
        "top_sessions": sorted(sessions, key=lambda item: item["total_credits"], reverse=True)[:5],
        "by_project": project_rows_from_sessions(sessions),
        "cache_report": cache_report_from_sessions(sessions, overall, active_thresholds),
        "account_switches": account_switches_from_snapshots(snapshots or [], start_day, end_day, start_at, end_at),
        "warnings": sorted(set(warnings + session_warnings)),
        "pricing_metadata": {
            "currency": prices.get("currency", "USD"),
            "unit": prices.get("unit", "per_1m_tokens"),
            "updated": prices.get("updated"),
            "credit_unit": prices.get("credit_unit", "per_1m_tokens"),
            "credit_source": prices.get("credit_source"),
            "notes": prices.get("notes", []),
        },
    }


def session_detail_report_from_records(
    records: list[codex_usage.UsageRecord],
    prices: dict[str, Any],
    metadata: dict[str, codex_usage.SessionMetadata],
    files_scanned: int,
    roots: list[Path],
    start_day: date,
    end_day: date,
    warnings: list[str],
    session_id: str,
    account_resolver: Callable[[codex_usage.UsageRecord], str] | None = None,
    account_filter: set[str] | None = None,
    start_at: datetime | None = None,
    end_at: datetime | None = None,
    thresholds: SessionSignalThresholds | None = None,
) -> dict[str, Any] | None:
    active_thresholds = thresholds or session_signal_thresholds()
    buckets, session_warnings = aggregate_session_buckets_from_records(records, prices, metadata, account_resolver, account_filter, session_id)
    bucket = buckets.get(session_id)
    if bucket is None:
        return None
    report = session_detail_from_bucket(bucket, active_thresholds)
    report.update(
        {
            "generated_at": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
            "period": exact_period(start_at, end_at) if start_at and end_at else {"from": start_day.isoformat(), "to": end_day.isoformat()},
            "source_roots": [str(root.expanduser()) for root in roots],
            "files_scanned": files_scanned,
            "usage_events": int(bucket["events"]),
            "warnings": sorted(set(warnings + session_warnings)),
            "pricing_metadata": {
                "currency": prices.get("currency", "USD"),
                "unit": prices.get("unit", "per_1m_tokens"),
                "updated": prices.get("updated"),
                "credit_unit": prices.get("credit_unit", "per_1m_tokens"),
                "credit_source": prices.get("credit_source"),
                "notes": prices.get("notes", []),
            },
        }
    )
    return report
