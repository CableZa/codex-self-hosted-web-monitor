from __future__ import annotations

import asyncio
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Callable

import codex_usage

from . import api_usage as usage_facade
from .api_dates import month_start, week_start
from .api_usage import (
    USAGE_AGGREGATE_CACHE_SCHEMA,
    _pruned_usage_aggregate_schemas,
    account_label,
    account_resolver_from_snapshots,
    add_aggregate_row,
    app_day_for_record,
    bucket_as_report_row,
    empty_usage_bucket,
    iter_days,
    scan_usage_files_for_period_sync,
    store,
    timed_dependency,
)


def week_end(day: date) -> date:
    return day + timedelta(days=6)


def period_label(start: date, end: date) -> str:
    return f"{start.isoformat()} to {end.isoformat()}"


def month_end(day: date) -> date:
    next_month = date(day.year + (1 if day.month == 12 else 0), 1 if day.month == 12 else day.month + 1, 1)
    return next_month - timedelta(days=1)


def period_bucket_row(kind: str, key: str, bucket: dict[str, Any]) -> dict[str, Any]:
    if kind == "week":
        start = date.fromisoformat(key)
        end = week_end(start)
        return {
            "day": key,
            "week": key,
            "start_day": start.isoformat(),
            "end_day": end.isoformat(),
            "label": period_label(start, end),
            **bucket_as_report_row(bucket),
        }
    start = date.fromisoformat(f"{key}-01")
    end = month_end(start)
    return {
        "day": key,
        "month": key,
        "start_day": start.isoformat(),
        "end_day": end.isoformat(),
        "label": start.strftime("%Y-%m"),
        **bucket_as_report_row(bucket),
    }


def aggregate_rows_from_records(
    records: list[codex_usage.UsageRecord],
    prices: dict[str, Any],
    account_resolver: Callable[[codex_usage.UsageRecord], str] | None = None,
    account_filter: set[str] | None = None,
) -> tuple[list[dict[str, Any]], list[str]]:
    buckets: dict[tuple[str, str, str, str], dict[str, Any]] = {}
    warnings: set[str] = set()
    for record in records:
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
        record_day = app_day_for_record(record)
        key = (record_day, account, model_key, record.effort)
        bucket = buckets.setdefault(
            key,
            {
                "day": record_day,
                "account": account,
                "model": model_key,
                "effort": record.effort,
                **empty_usage_bucket(),
            },
        )
        metric_row = {
            **record.usage.as_dict(),
            **cost.as_dict(),
            "events": 1,
            "sessions": {record.session_id},
            "files": {record.path},
        }
        add_aggregate_row(bucket, metric_row)
    return list(buckets.values()), sorted(warnings)


def aggregate_rows_for_period_sync(
    start: date,
    end: date,
    snapshots: list[dict[str, Any]],
    account_filter: set[str] | None = None,
    start_at: datetime | None = None,
    end_at: datetime | None = None,
    unknown_account_mapping: str = "",
) -> tuple[list[dict[str, Any]], list[str]]:
    prices = codex_usage.load_prices(codex_usage.DEFAULT_PRICES_PATH)
    records, _metadata, _files, _roots, warnings = usage_facade.scan_usage_files_for_period_sync(
        start,
        end,
        start_at,
        end_at,
        include_metadata=False,
    )
    rows, pricing_warnings = aggregate_rows_from_records(records, prices, account_resolver_from_snapshots(snapshots, unknown_account_mapping), account_filter)
    return rows, sorted(set(warnings + pricing_warnings))


async def aggregate_rows_for_period(
    start: date,
    end: date,
    snapshots: list[dict[str, Any]],
    account_filter: set[str] | None = None,
    start_at: datetime | None = None,
    end_at: datetime | None = None,
    unknown_account_mapping: str = "",
) -> tuple[list[dict[str, Any]], list[str]]:
    return await asyncio.to_thread(aggregate_rows_for_period_sync, start, end, snapshots, account_filter, start_at, end_at, unknown_account_mapping)


def report_from_aggregate_rows(
    rows: list[dict[str, Any]],
    prices: dict[str, Any],
    start: date,
    end: date,
    warnings: list[str],
    roots: list[Path],
) -> dict[str, Any]:
    overall = empty_usage_bucket()
    by_day: dict[str, dict[str, Any]] = {}
    by_model: dict[str, dict[str, Any]] = {}
    by_effort: dict[str, dict[str, Any]] = {}
    by_account: dict[str, dict[str, Any]] = {}
    by_day_model: dict[tuple[str, str], dict[str, Any]] = {}
    by_day_account: dict[tuple[str, str], dict[str, Any]] = {}
    by_model_effort: dict[tuple[str, str], dict[str, Any]] = {}
    by_week: dict[str, dict[str, Any]] = {}
    by_month: dict[str, dict[str, Any]] = {}
    for row in rows:
        add_aggregate_row(overall, row)
        day = str(row["day"])
        day_value = date.fromisoformat(day)
        week_key = week_start(day_value).isoformat()
        month_key = month_start(day_value).isoformat()[:7]
        account = str(row["account"])
        model = str(row["model"])
        effort = str(row["effort"])
        add_aggregate_row(by_day.setdefault(day, empty_usage_bucket()), row)
        add_aggregate_row(by_week.setdefault(week_key, empty_usage_bucket()), row)
        add_aggregate_row(by_month.setdefault(month_key, empty_usage_bucket()), row)
        add_aggregate_row(by_model.setdefault(model, empty_usage_bucket()), row)
        add_aggregate_row(by_effort.setdefault(effort, empty_usage_bucket()), row)
        add_aggregate_row(by_account.setdefault(account, empty_usage_bucket()), row)
        add_aggregate_row(by_day_model.setdefault((day, model), empty_usage_bucket()), row)
        add_aggregate_row(by_day_account.setdefault((day, account), empty_usage_bucket()), row)
        add_aggregate_row(by_model_effort.setdefault((model, effort), empty_usage_bucket()), row)

    return {
        "generated_at": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        "period": {"from": start.isoformat(), "to": end.isoformat()},
        "source_roots": [str(root.expanduser()) for root in roots],
        "files_scanned": len(overall["files"]),
        "usage_events": int(overall["events"]),
        "totals": bucket_as_report_row(overall),
        "by_day": [{"day": day, **bucket_as_report_row(bucket)} for day, bucket in sorted(by_day.items(), reverse=True)],
        "by_week": [
            period_bucket_row("week", week, bucket)
            for week, bucket in sorted(by_week.items(), reverse=True)
        ],
        "by_month": [
            period_bucket_row("month", month, bucket)
            for month, bucket in sorted(by_month.items(), reverse=True)
        ],
        "by_model": [
            {"model": model, **bucket_as_report_row(bucket)}
            for model, bucket in sorted(by_model.items(), key=lambda item: item[1]["total_credits"], reverse=True)
        ],
        "by_effort": [
            {"effort": effort, **bucket_as_report_row(bucket)}
            for effort, bucket in sorted(by_effort.items(), key=lambda item: item[1]["total_credits"], reverse=True)
        ],
        "by_account": [
            {"account": account, **bucket_as_report_row(bucket)}
            for account, bucket in sorted(by_account.items(), key=lambda item: item[1]["total_credits"], reverse=True)
        ],
        "by_day_model": [
            {"day": day, "model": model, **bucket_as_report_row(bucket)}
            for (day, model), bucket in sorted(by_day_model.items(), reverse=True)
        ],
        "by_day_account": [
            {"day": day, "account": account, **bucket_as_report_row(bucket)}
            for (day, account), bucket in sorted(by_day_account.items(), reverse=True)
        ],
        "by_model_effort": [
            {"model": model, "effort": effort, **bucket_as_report_row(bucket)}
            for (model, effort), bucket in sorted(
                by_model_effort.items(),
                key=lambda item: item[1]["total_credits"],
                reverse=True,
            )
        ],
        "warnings": sorted(set(warnings)),
        "pricing_metadata": {
            "currency": prices.get("currency", "USD"),
            "unit": prices.get("unit", "per_1m_tokens"),
            "updated": prices.get("updated"),
            "credit_unit": prices.get("credit_unit", "per_1m_tokens"),
            "credit_source": prices.get("credit_source"),
            "notes": prices.get("notes", []),
        },
    }


def report_account_labels(report: dict[str, Any], snapshots: list[dict[str, Any]]) -> list[str]:
    accounts = {account_label(snapshot) for snapshot in snapshots}
    accounts.update(str(row.get("account")) for row in report.get("by_account", []) if row.get("account"))
    return sorted(accounts)


async def ensure_historic_usage_aggregates(
    cache_version: str,
    start: date,
    end: date,
    snapshots: list[dict[str, Any]],
    unknown_account_mapping: str = "",
) -> list[str]:
    warnings: list[str] = []
    if USAGE_AGGREGATE_CACHE_SCHEMA not in _pruned_usage_aggregate_schemas:
        await store.prune_usage_aggregate_cache_schemas(USAGE_AGGREGATE_CACHE_SCHEMA)
        _pruned_usage_aggregate_schemas.add(USAGE_AGGREGATE_CACHE_SCHEMA)
    present = await store.usage_aggregate_days(cache_version, start, end)
    missing = [day for day in iter_days(start, end) if day.isoformat() not in present]
    for day in missing:
        with timed_dependency("service.persist_usage_day", day=day.isoformat()):
            rows, day_warnings = await usage_facade.aggregate_rows_for_period(day, day, snapshots, unknown_account_mapping=unknown_account_mapping)
            warnings.extend(day_warnings)
            await store.save_usage_daily_aggregate(cache_version, day, rows, day_warnings)
    return sorted(set(warnings))
