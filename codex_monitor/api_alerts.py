from __future__ import annotations

import asyncio
import os
from datetime import date, datetime, time, timedelta, timezone
from typing import Any
from zoneinfo import ZoneInfo

import codex_usage
import httpx

from .api_dates import DEFAULT_TZ, bool_setting, float_setting, now_local, period_bounds
from .api_http import validate_outbound_url
from .api_limits import (
    AccountLimitStatus,
    advisory_dict,
    BudgetStatus,
    account_limit_status_from_dict,
    account_limit_status_dict,
    account_limit_status_from_report,
    parse_thresholds,
    reset_window_for_datetime,
    resolve_window_reference_time,
)
from .api_refs import active_http_client, cache, store
from .api_timing import logger, timed_dependency
from .version import APP_VERSION
from .api_usage import usage_report, usage_report_for_window

SUMMARY_TIMES = (time(10, 0), time(15, 0))
TODAY_CACHE_TTL_SECONDS = int(os.environ.get("TODAY_CACHE_TTL_SECONDS", "90"))
DEFAULT_DAYS_BACK = int(os.environ.get("DEFAULT_DAYS_BACK", "30"))


def budget_statuses(settings: dict[str, str], reports: dict[str, dict[str, Any]], today: date) -> list[BudgetStatus]:
    use_credits = settings.get("pricing_mode", "credits") == "credits"
    if use_credits:
        return []
    credit_budgets = {
        "today": float_setting(settings, "daily_budget_credits", 100),
        "week": float_setting(settings, "weekly_budget_credits", 700),
        "month": float_setting(settings, "monthly_budget_credits", 3000),
    }
    zar_budgets = {
        "today": float_setting(settings, "daily_budget_zar", 0),
        "week": float_setting(settings, "weekly_budget_zar", 0),
        "month": float_setting(settings, "monthly_budget_zar", 0),
    }
    statuses = []
    for period in ("today", "week", "month"):
        start, end = period_bounds(period, today)
        budget = credit_budgets[period] if use_credits else zar_budgets[period]
        current = float(reports[period]["totals"].get("total_credits" if use_credits else "total_zar", 0))
        ratio = current / budget if budget > 0 else 0
        statuses.append(
            BudgetStatus(
                period=period,
                start=start,
                end=end,
                budget_zar=zar_budgets[period],
                current_zar=float(reports[period]["totals"].get("total_zar", 0)),
                budget_credits=credit_budgets[period],
                current_credits=float(reports[period]["totals"].get("total_credits", 0)),
                unit="credits" if use_credits else "zar",
                ratio=ratio,
                exceeded=budget > 0 and current >= budget,
                next_repeat_ratio=1.0 if ratio < 1 else 1.0 + ((int((ratio - 1) / 0.25) + 1) * 0.25),
            )
        )
    return statuses


async def send_webhook(settings: dict[str, str], payload: dict[str, Any]) -> dict[str, Any]:
    url = settings.get("webhook_url", "").strip()
    if not url:
        return {"sent": False, "reason": "webhook_url not configured"}
    try:
        validate_outbound_url(url, "webhook_url")
        with timed_dependency("web.webhook", event_type=payload.get("type", "unknown")):
            response = await active_http_client().post(url, json=payload, timeout=8)
            response.raise_for_status()
            return {"sent": True, "status": response.status_code}
    except (ValueError, httpx.HTTPError, TimeoutError) as exc:
        return {"sent": False, "reason": str(exc)}


def alert_payload(status: BudgetStatus, report: dict[str, Any], settings: dict[str, str]) -> dict[str, Any]:
    totals = report["totals"]
    return {
        "type": "budget_alert",
        "period": status.period,
        "period_start": status.start.isoformat(),
        "period_end": status.end.isoformat(),
        "budget_zar": status.budget_zar,
        "current_zar": status.current_zar,
        "budget_credits": status.budget_credits,
        "current_credits": status.current_credits,
        "unit": status.unit,
        "percent_used": round(status.ratio * 100, 1),
        "total_usd": totals.get("total_usd", 0),
        "total_credits": totals.get("total_credits", 0),
        "input_tokens": totals.get("input_tokens", 0),
        "output_tokens": totals.get("output_tokens", 0),
        "total_tokens": totals.get("total_tokens", 0),
        "dashboard_url": settings.get("dashboard_url", "http://127.0.0.1:8787"),
        "created_at": datetime.now(timezone.utc).isoformat(),
    }


def account_limit_alert_payload(status: AccountLimitStatus, threshold: float, settings: dict[str, str]) -> dict[str, Any]:
    return {
        "type": "account_limit_alert",
        "account": status.account,
        "metric": status.metric,
        "window_start": status.window_start_at,
        "window_end": status.window_end_at,
        "window_start_day": status.window_start.isoformat(),
        "window_end_day": status.window_end.isoformat(),
        "reset_at": status.reset_at,
        "threshold_ratio": threshold,
        "percent_used": round(status.ratio * 100, 1),
        "cap_value": status.cap_value,
        "current_value": status.current_value,
        "remaining_value": status.remaining_value,
        "dashboard_url": settings.get("dashboard_url", "http://127.0.0.1:8787"),
        "created_at": datetime.now(timezone.utc).isoformat(),
    }


def account_burn_alert_payload(status: AccountLimitStatus, advisory: dict[str, Any], settings: dict[str, str]) -> dict[str, Any]:
    return {
        "type": "account_burn_alert",
        "account": status.account,
        "metric": status.metric,
        "severity": advisory["severity"],
        "advisory_id": advisory["id"],
        "message": advisory["message"],
        "label": advisory["label"],
        "value": advisory["value"],
        "window_start": status.window_start_at,
        "window_end": status.window_end_at,
        "window_start_day": status.window_start.isoformat(),
        "window_end_day": status.window_end.isoformat(),
        "reset_at": status.reset_at,
        "percent_used": round(status.ratio * 100, 1),
        "cap_value": status.cap_value,
        "current_value": status.current_value,
        "remaining_value": status.remaining_value,
        "safe_daily_spend": status.safe_daily_spend,
        "spend_rate_vs_target": status.spend_rate_vs_target,
        "projected_exhaustion_date": status.projected_exhaustion_date,
        "projected_exhaustion_label": status.projected_exhaustion_label,
        "dashboard_url": settings.get("dashboard_url", "http://127.0.0.1:8787"),
        "created_at": datetime.now(timezone.utc).isoformat(),
    }


async def check_alerts(reports: dict[str, dict[str, Any]]) -> list[dict[str, Any]]:
    settings = await store.settings()
    today = now_local().date()
    emitted = []
    for status in budget_statuses(settings, reports, today):
        if not status.exceeded:
            continue
        last_ratio = await store.latest_alert_ratio(status.period, status.start, status.end)
        threshold_ratio = 1.0 if last_ratio == 0 else last_ratio + 0.25
        if status.ratio < threshold_ratio:
            continue
        payload = alert_payload(status, reports[status.period], settings)
        await store.record_alert(payload, threshold_ratio)
        payload["webhook"] = await send_webhook(settings, payload)
        emitted.append(payload)
    return emitted


async def account_limit_statuses(today: date | datetime | None = None) -> list[dict[str, Any]]:
    limits = await store.account_limits(enabled_only=True)
    return [await account_limit_status_for_limit(limit, today) for limit in limits]


async def account_limit_status_for_limit(limit: dict[str, Any], today: date | datetime | None = None) -> dict[str, Any]:
    tz_name = str(limit.get("timezone") or DEFAULT_TZ)
    local_now = resolve_window_reference_time(today, tz_name)
    window_start_at, window_end_at = reset_window_for_datetime(
        local_now,
        int(limit.get("reset_weekday", 4)),
        str(limit.get("reset_time") or "00:00"),
    )
    report = await usage_report_for_window(window_start_at, min(window_end_at, local_now), {str(limit["account"])})
    status = account_limit_status_from_report(limit, report, local_now.date(), window_start_at, window_end_at)
    return account_limit_status_dict(status)


async def migrate_account_limits_to_credits(today: date | datetime | None = None) -> None:
    settings = await store.settings()
    if bool_setting(settings, "account_credit_limit_migration_done", False):
        return
    migrated_any = False
    skipped_any = False
    for limit in await store.account_limits(enabled_only=False):
        if str(limit.get("metric") or "total_tokens") != "total_tokens":
            continue
        account = str(limit["account"])
        tz_name = str(limit.get("timezone") or DEFAULT_TZ)
        local_now = resolve_window_reference_time(today, tz_name)
        local_today = local_now.date()
        window_start_at, window_end_at = reset_window_for_datetime(
            local_now,
            int(limit.get("reset_weekday", 4)),
            str(limit.get("reset_time") or "00:00"),
        )
        report = await usage_report_for_window(window_start_at, min(window_end_at, local_now), {account})
        totals = report.get("totals", {})
        tokens = float(totals.get("total_tokens", 0))
        credits = float(totals.get("total_credits", 0))
        if tokens <= 0 or credits <= 0:
            fallback_start = local_today - timedelta(days=90)
            report = await usage_report(fallback_start, local_today, {account})
            totals = report.get("totals", {})
            tokens = float(totals.get("total_tokens", 0))
            credits = float(totals.get("total_credits", 0))
        if tokens <= 0 or credits <= 0:
            skipped_any = True
            logger.warning("account_limit_credit_migration_skipped account=%s reason=no_usage_ratio", account)
            continue
        cap_credits = float(limit["cap_value"]) * (credits / tokens)
        payload = {
            "account": account,
            "metric": "total_credits",
            "cap_value": round(cap_credits, 2),
            "reset_weekday": int(limit.get("reset_weekday", 4)),
            "reset_time": str(limit.get("reset_time") or "00:00"),
            "timezone": str(limit.get("timezone") or DEFAULT_TZ),
            "thresholds": parse_thresholds(limit.get("thresholds")),
            "enabled": bool(limit.get("enabled", 1)),
        }
        await store.upsert_account_limit(payload)
        migrated_any = True
        logger.info(
            "account_limit_credit_migrated account=%s old_tokens=%.1f new_credits=%.2f ratio=%.8f",
            account,
            float(limit["cap_value"]),
            cap_credits,
            credits / tokens,
        )
    if migrated_any or not skipped_any:
        await store.update_settings({"account_credit_limit_migration_done": "true"})


async def check_account_limit_alerts(statuses: list[dict[str, Any]]) -> list[dict[str, Any]]:
    settings = await store.settings()
    emitted = []
    for status_data in statuses:
        status = account_limit_status_from_dict(status_data)
        last_ratio = await store.latest_account_limit_threshold(
            status.account,
            status.metric,
            status.window_start_at,
            status.window_end_at,
        )
        for threshold in status.crossed_thresholds:
            if threshold <= last_ratio:
                continue
            payload = account_limit_alert_payload(status, threshold, settings)
            inserted = await store.record_account_limit_alert(payload, threshold)
            if not inserted:
                continue
            payload["webhook"] = await send_webhook(settings, payload)
            emitted.append(payload)
    return emitted


async def check_account_burn_alerts(statuses: list[dict[str, Any]]) -> list[dict[str, Any]]:
    settings = await store.settings()
    emitted = []
    for status_data in statuses:
        status = account_limit_status_from_dict(status_data)
        for advisory in [advisory_dict(item) for item in status.burn_advisories]:
            if advisory["severity"] not in {"warning", "critical"}:
                continue
            if advisory["id"] == "window-exhausted":
                continue
            payload = account_burn_alert_payload(status, advisory, settings)
            inserted = await store.record_account_burn_alert(payload)
            if not inserted:
                continue
            payload["webhook"] = await send_webhook(settings, payload)
            emitted.append(payload)
    return emitted


def codex_rate_card() -> dict[str, Any]:
    prices = codex_usage.load_prices(codex_usage.DEFAULT_PRICES_PATH)
    rows = []
    for model, rates in prices.get("models", {}).items():
        if not any(key in rates for key in ("input_credits", "cached_input_credits", "output_credits")):
            continue
        rows.append(
            {
                "model": model,
                "input_credits": rates.get("input_credits"),
                "cached_input_credits": rates.get("cached_input_credits"),
                "output_credits": rates.get("output_credits"),
                "source": rates.get("source"),
            }
        )
    return {
        "unit": prices.get("credit_unit", "per_1m_tokens"),
        "source": prices.get("credit_source"),
        "updated": prices.get("updated"),
        "fast_mode_detectable": False,
        "fast_mode_note": "Fast mode can consume more credits, but current local session logs do not reliably expose selected service tier.",
        "rows": rows,
    }


async def build_snapshot() -> dict[str, Any]:
    with timed_dependency("service.build_snapshot"):
        snapshot_now = now_local()
        today = snapshot_now.date()
        reports: dict[str, dict[str, Any]] = {}
        for period in ("today", "week", "month"):
            start, end = period_bounds(period, today)
            reports[period] = await usage_report(start, end)
        settings = await store.settings()
        statuses = budget_statuses(settings, reports, today)
        alerts = await check_alerts(reports)
        await migrate_account_limits_to_credits(snapshot_now)
        limit_statuses = await account_limit_statuses(snapshot_now)
        account_alerts = await check_account_limit_alerts(limit_statuses)
        burn_alerts = await check_account_burn_alerts(limit_statuses)
        return {
            "version": APP_VERSION,
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "timezone": DEFAULT_TZ,
            "reports": reports,
            "budgets": [status.__dict__ | {"start": status.start.isoformat(), "end": status.end.isoformat()} for status in statuses],
            "account_limits": limit_statuses,
            "alerts_emitted": alerts + account_alerts + burn_alerts,
            "cache": await cache.status(),
        }


latest_snapshot: dict[str, Any] = {}


async def maybe_send_summaries(snapshot: dict[str, Any]) -> None:
    local_now = now_local()
    settings = await store.settings()
    for slot_time in SUMMARY_TIMES:
        if local_now.time() < slot_time:
            continue
        slot = slot_time.strftime("%H:%M")
        today_report = snapshot["reports"]["today"]
        payload = {
            "type": "usage_summary",
            "summary_for": local_now.date().isoformat(),
            "slot": slot,
            "current_zar": today_report["totals"].get("total_zar", 0),
            "total_usd": today_report["totals"].get("total_usd", 0),
            "current_credits": today_report["totals"].get("total_credits", 0),
            "input_tokens": today_report["totals"].get("input_tokens", 0),
            "output_tokens": today_report["totals"].get("output_tokens", 0),
            "dashboard_url": settings.get("dashboard_url", "http://127.0.0.1:8787"),
            "created_at": datetime.now(timezone.utc).isoformat(),
        }
        inserted = await store.record_summary_once(local_now.date(), slot, payload)
        if inserted:
            await send_webhook(settings, payload)
