from __future__ import annotations

import asyncio
import json
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any, Callable

import codex_usage
from codex_usage_models import ParseDiagnostics

from .api_accounts import account_resolver_from_snapshots
from .api_cache_keys import (
    diagnostics_cache_key,
    diagnostics_window_cache_key,
    response_cache_meta,
    ttl_for_range,
    ttl_for_window,
    versioned_cache_key,
)
from .api_refs import cache, inflight_diagnostics_reports, store
from .api_usage import cacheable_window_end, exact_period, scan_usage_files_for_period_sync, usage_cache_generation, window_dates


def usage_diagnostics_from_scan(
    records: list[codex_usage.UsageRecord],
    metadata: dict[str, codex_usage.SessionMetadata],
    files: list[Path],
    roots: list[Path],
    warnings: list[str],
    diagnostics: ParseDiagnostics,
    prices: dict[str, Any],
    start: date,
    end: date,
    account_resolver: Callable[[codex_usage.UsageRecord], str] | None = None,
    account_filter: set[str] | None = None,
    start_at: datetime | None = None,
    end_at: datetime | None = None,
) -> dict[str, Any]:
    unpriced_models: set[str] = set()
    model_aliases: set[str] = set()
    unknown_account_events = 0
    long_context_events = 0
    for record in records:
        account = account_resolver(record) if account_resolver else record.account
        if not account or account == "unknown":
            unknown_account_events += 1
        if account_filter and account not in account_filter:
            continue
        priced_model, rates = codex_usage.lookup_rates(record.model, prices)
        if rates is None:
            unpriced_models.add(record.model)
            continue
        if priced_model != record.model:
            model_aliases.add(f"{record.model} as {priced_model}")
        if codex_usage.cost_for_usage(record.usage, rates).long_context_applied:
            long_context_events += 1

    skipped_events = (
        diagnostics.invalid_json_events
        + diagnostics.non_object_json_events
        + diagnostics.non_object_payload_events
        + diagnostics.malformed_usage_events
        + diagnostics.skipped_subagent_replay_events
    )
    reasons: list[str] = []
    if not files:
        reasons.append("No JSONL files matched the requested range.")
    if not records:
        reasons.append("No usage records were accepted in the requested range.")
    if unpriced_models:
        reasons.append("Some models do not have local pricing metadata.")
    if warnings:
        reasons.extend(warnings[:3])
    if skipped_events:
        reasons.append(f"{skipped_events} source event(s) were skipped by parser safeguards.")
    if unknown_account_events:
        reasons.append(f"{unknown_account_events} event(s) have unknown account attribution.")

    if not files or not records or diagnostics.malformed_usage_events > 0 or unpriced_models:
        confidence = "low"
    elif skipped_events or warnings or unknown_account_events:
        confidence = "medium"
    else:
        confidence = "high"

    activity = list(metadata.values())
    return {
        "generated_at": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        "period": exact_period(start_at, end_at) if start_at and end_at else {"from": start.isoformat(), "to": end.isoformat()},
        "source_roots": [str(root.expanduser()) for root in roots],
        "scan": {
            **diagnostics.as_dict(),
            "filtered_files": len(files),
            "sessions": len({record.session_id for record in records}),
            "metadata_sessions": len(metadata),
        },
        "parser": diagnostics.as_dict(),
        "pricing": {
            "unpriced_models": sorted(unpriced_models),
            "model_aliases": sorted(model_aliases),
            "long_context_events": long_context_events,
            "pricing_updated": prices.get("updated"),
        },
        "attribution": {
            "unknown_account_events": unknown_account_events,
            "account_filter": sorted(account_filter or []),
        },
        "activity": {
            "tool_calls": sum(item.tool_call_count for item in activity),
            "tool_errors": sum(item.tool_error_count for item in activity),
            "web_tool_calls": sum(item.web_tool_call_count for item in activity),
            "large_ingests": sum(item.large_ingest_count for item in activity),
            "large_starting_prompts": sum(1 for item in activity if item.first_message_word_count >= 800),
        },
        "confidence_grade": confidence,
        "confidence_reasons": reasons or ["No parser, pricing, or attribution issues were detected."],
        "warnings": warnings,
    }


async def compute_usage_diagnostics_report(start: date, end: date, account_filter: set[str] | None = None) -> dict[str, Any]:
    settings = await store.settings()
    snapshots = await store.auth_snapshots(limit=1000)
    prices = codex_usage.load_prices(codex_usage.DEFAULT_PRICES_PATH)
    diagnostics = ParseDiagnostics()
    records, metadata, files, roots, warnings = await asyncio.to_thread(scan_usage_files_for_period_sync, start, end, None, None, diagnostics)
    return usage_diagnostics_from_scan(
        records,
        metadata,
        files,
        roots,
        warnings,
        diagnostics,
        prices,
        start,
        end,
        account_resolver_from_snapshots(snapshots, settings.get("unknown_account_mapping", "")),
        account_filter,
    )


async def usage_diagnostics_report(start: date, end: date, account_filter: set[str] | None = None) -> dict[str, Any]:
    generation = await usage_cache_generation()
    key = versioned_cache_key(generation, diagnostics_cache_key(start, end, account_filter))
    ttl = ttl_for_range(start, end)
    cached = await cache.get(key)
    if cached:
        cached = json.loads(json.dumps(cached))
        cached["cache"] = response_cache_meta(True, ttl)
        return cached

    task = inflight_diagnostics_reports.get(key)
    if task is None:
        async def build_and_cache() -> dict[str, Any]:
            report = await compute_usage_diagnostics_report(start, end, account_filter)
            report["cache"] = response_cache_meta(False, ttl)
            await cache.set(key, report, ttl)
            return report

        task = asyncio.create_task(build_and_cache())
        inflight_diagnostics_reports[key] = task
    try:
        return await task
    finally:
        if inflight_diagnostics_reports.get(key) is task:
            inflight_diagnostics_reports.pop(key, None)


async def compute_usage_diagnostics_report_for_window(start_at: datetime, end_at: datetime, account_filter: set[str] | None = None) -> dict[str, Any]:
    settings = await store.settings()
    snapshots = await store.auth_snapshots(limit=1000)
    prices = codex_usage.load_prices(codex_usage.DEFAULT_PRICES_PATH)
    diagnostics = ParseDiagnostics()
    start, end = window_dates(start_at, end_at)
    records, metadata, files, roots, warnings = await asyncio.to_thread(scan_usage_files_for_period_sync, start, end, start_at, end_at, diagnostics)
    return usage_diagnostics_from_scan(
        records,
        metadata,
        files,
        roots,
        warnings,
        diagnostics,
        prices,
        start,
        end,
        account_resolver_from_snapshots(snapshots, settings.get("unknown_account_mapping", "")),
        account_filter,
        start_at,
        end_at,
    )


async def usage_diagnostics_report_for_window(start_at: datetime, end_at: datetime, account_filter: set[str] | None = None) -> dict[str, Any]:
    generation = await usage_cache_generation()
    key_end_at = cacheable_window_end(start_at, end_at)
    key = versioned_cache_key(generation, diagnostics_window_cache_key(start_at, key_end_at, account_filter))
    ttl = ttl_for_window(start_at, end_at)
    cached = await cache.get(key)
    if cached:
        cached = json.loads(json.dumps(cached))
        cached["cache"] = response_cache_meta(True, ttl)
        return cached

    task = inflight_diagnostics_reports.get(key)
    if task is None:
        async def build_and_cache() -> dict[str, Any]:
            report = await compute_usage_diagnostics_report_for_window(start_at, key_end_at, account_filter)
            report["cache"] = response_cache_meta(False, ttl)
            await cache.set(key, report, ttl)
            return report

        task = asyncio.create_task(build_and_cache())
        inflight_diagnostics_reports[key] = task
    try:
        return await task
    finally:
        if inflight_diagnostics_reports.get(key) is task:
            inflight_diagnostics_reports.pop(key, None)
