from __future__ import annotations

import asyncio
import json
import os
import time as monotonic_time
from contextlib import asynccontextmanager
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from typing import Any
from zoneinfo import ZoneInfo

try:
    import httpx
except ImportError:  # pragma: no cover
    class _MissingAsyncClient:
        def __init__(self, *_args, **_kwargs) -> None:
            return None

        async def aclose(self) -> None:
            return None

    httpx = SimpleNamespace(AsyncClient=_MissingAsyncClient)

try:
    from fastapi import FastAPI, HTTPException, Request
    from fastapi.responses import FileResponse, StreamingResponse
    from fastapi.staticfiles import StaticFiles
except ImportError as exc:  # pragma: no cover
    raise SystemExit("FastAPI is not installed. Run: pip install -r requirements.txt") from exc

import codex_usage

from . import (
    api_accounts as accounts_module,
    api_alerts as alerts_module,
    api_cache as cache_module,
    api_cache_keys as cache_keys_module,
    api_dates as dates_module,
    api_limits as limits_module,
    api_store as store_module,
    api_timing as timing_module,
    api_usage as usage_module,
)
from .api_accounts import (
    account_label,
    account_options_from_snapshots,
    account_resolver_from_snapshots,
    auto_account_limit_defaults,
    confirmed_account_labels,
    decode_jwt_payload,
    ensure_default_account_limits_from_snapshots,
    first_auth_snapshot_at,
    merge_usage_account_options,
    parse_accounts_param,
    parse_snapshot_time,
    read_codex_auth_identity,
    record_current_auth_snapshot,
    validate_unknown_account_mapping,
    validate_settings_updates,
    visible_usage_history,
)
from .api_alerts import (
    account_burn_alert_payload,
    account_limit_alert_payload,
    account_limit_status_for_limit,
    account_limit_statuses,
    alert_payload,
    budget_statuses,
    build_snapshot,
    check_account_burn_alerts,
    check_account_limit_alerts,
    check_alerts,
    codex_rate_card,
    maybe_send_summaries,
    migrate_account_limits_to_credits,
    send_webhook,
)
from .api_cache import JsonCache
from .api_cache_keys import (
    account_cache_part,
    account_limit_statuses_cache_key,
    day_cache_key,
    days_cache_key,
    latest_snapshot_cache_key,
    period_includes_today,
    report_cache_key,
    response_cache_meta,
    snapshot_cache_key,
    ttl_for_day,
    ttl_for_range,
    versioned_cache_key,
)
from .api_dates import (
    bool_setting,
    float_setting,
    iter_days,
    month_start,
    now_local,
    parse_api_datetime,
    parse_api_day,
    parse_local_day,
    period_bounds,
    previous_month_bounds,
    validate_datetime_range,
    validate_date_range,
    week_start,
)
from .api_http import fetch_json_sync, post_json_sync, probe_http_status_sync, validate_outbound_url
from .api_limits import (
    AccountLimitStatus,
    BudgetStatus,
    account_limit_status_dict,
    account_limit_status_from_report,
    parse_reset_time,
    parse_thresholds,
    reset_at_iso,
    reset_window_for_datetime,
    reset_window_for_day,
    validate_account_limit_payload,
)
from .api_store import Store
from .api_timing import bool_env, logger, timed_dependency
from .session_signals import SESSION_SIGNAL_THRESHOLD_KEYS
from .api_usage import (
    USAGE_METRIC_FIELDS,
    add_aggregate_row,
    add_zar,
    aggregate_rows_for_period,
    aggregate_rows_for_period_sync,
    aggregate_rows_from_records,
    bucket_as_report_row,
    cache_day_rows_from_report,
    cached_day_rows,
    compute_usage_report,
    day_row_from_report,
    days_report_has_activity,
    days_report,
    days_report_for_window,
    days_response,
    empty_day_row,
    empty_usage_bucket,
    ensure_daily_cache_for_range,
    ensure_historic_usage_aggregates,
    exchange_rate_for_response,
    fetch_usd_zar,
    materialize_common_ranges,
    report_from_aggregate_rows,
    report_account_labels,
    row_set,
    row_has_usage_activity,
    rows_from_report,
    snapshot_has_usage_activity,
    session_detail_report,
    session_detail_report_for_window,
    session_history_report,
    session_history_report_for_window,
    usage_aggregate_cache_version,
    usage_report_has_activity,
    usage_report,
    usage_report_for_window,
)
from .api_usage_diagnostics import usage_diagnostics_report, usage_diagnostics_report_for_window
from .config import AppConfig
from .schemas import (
    AccountLimitPutResult,
    AccountLimitUpdate,
    AccountLimitsReport,
    AccountsReport,
    AlertResponse,
    AuthSnapshotCreate,
    AuthSnapshotResult,
    ChangelogReport,
    DaysReport,
    HealthResponse,
    RateCard,
    SettingsUpdate,
    SnapshotResponse,
    SessionDetail,
    SessionHistoryReport,
    UpdateStatusResponse,
    UsageDiagnosticsReport,
    UsageReport,
    WebhookResult,
)
from .version import APP_VERSION

SCRIPT_DIR = store_module.SCRIPT_DIR
STATIC_DIR = SCRIPT_DIR / "static"
CHANGELOG_PATH = SCRIPT_DIR / "CHANGELOG.md"
UPDATE_STATUS_PATH = SCRIPT_DIR / "runtime" / "update-status.json"
UPDATE_CHECK_ENABLED, UPDATE_CHECK_INTERVAL_SECONDS, UPDATE_CHECK_TIMEOUT_SECONDS, UPDATE_CHECK_TAGS_URL, UPDATE_INSTALL_MODE = (True, 21600, 8, "https://api.github.com/repos/CableZa/codex-self-hosted-web-monitor/tags?per_page=100", "auto")
SCHEMA_PATH = store_module.SCHEMA_PATH
DEFAULT_DB = store_module.DEFAULT_DB
DEFAULT_TZ = dates_module.DEFAULT_TZ
SUMMARY_TIMES = alerts_module.SUMMARY_TIMES
VALKEY_URL = cache_module.os.environ.get("VALKEY_URL", "redis://127.0.0.1:6379/0")
TODAY_CACHE_TTL_SECONDS = cache_keys_module.TODAY_CACHE_TTL_SECONDS
HISTORIC_CACHE_TTL_SECONDS = cache_keys_module.HISTORIC_CACHE_TTL_SECONDS
DEFAULT_DAYS_BACK = usage_module.DEFAULT_DAYS_BACK
USAGE_CACHE_GENERATION_KEY = usage_module.USAGE_CACHE_GENERATION_KEY
MAX_DATE_RANGE_DAYS = dates_module.MAX_DATE_RANGE_DAYS
MAX_ACCOUNT_FILTERS = accounts_module.MAX_ACCOUNT_FILTERS
MAX_ALERT_LIMIT = int(cache_module.os.environ.get("MAX_ALERT_LIMIT", "200"))
MATERIALIZED_DAYS_BACK = usage_module.MATERIALIZED_DAYS_BACK
LOG_LEVEL = timing_module.LOG_LEVEL
AUTH_SNAPSHOT_SOURCE = accounts_module.AUTH_SNAPSHOT_SOURCE
FX_LIVE_ENABLED = usage_module.FX_LIVE_ENABLED
FX_FALLBACK_RETRY_SECONDS = usage_module.FX_FALLBACK_RETRY_SECONDS
USAGE_AGGREGATE_CACHE_SCHEMA = usage_module.USAGE_AGGREGATE_CACHE_SCHEMA
CACHE_KEY_PREFIX = cache_module.CACHE_KEY_PREFIX
CACHE_MEMORY_FALLBACK_MODE = cache_module.CACHE_MEMORY_FALLBACK_MODE
MONITOR_API_WORKERS = cache_module.MONITOR_API_WORKERS
DEBUG_TIMING_ENABLED = timing_module.DEBUG_TIMING_ENABLED
UPDATE_STATUS_MAX_AGE_SECONDS = int(cache_module.os.environ.get("UPDATE_STATUS_MAX_AGE_SECONDS", "86400"))
LATEST_SNAPSHOT_TTL_SECONDS = max(TODAY_CACHE_TTL_SECONDS * 3, 180)
ACCOUNT_LIMIT_GENERATION_KEY = "account_limit_generation"
ACCOUNT_LIMIT_STATUS_TTL_SECONDS = LATEST_SNAPSHOT_TTL_SECONDS

store = Store()
cache = JsonCache(VALKEY_URL)
inflight_usage_reports: dict[str, asyncio.Task[dict[str, Any]]] = {}
inflight_session_reports: dict[str, asyncio.Task[dict[str, Any] | None]] = {}
inflight_diagnostics_reports: dict[str, asyncio.Task[dict[str, Any]]] = {}
shared_http_client: Any | None = None
latest_snapshot: dict[str, Any] = {}
requested_snapshot_generation = 1
HIDDEN_PUBLIC_SETTINGS_KEYS = {
    ACCOUNT_LIMIT_GENERATION_KEY,
    "account_credit_limit_migration_done",
    "cache_generation",
    "daily_budget_credits",
    "monthly_budget_credits",
    USAGE_CACHE_GENERATION_KEY,
    "weekly_budget_credits",
}


def create_http_client(config: AppConfig | None = None) -> Any:
    if config is not None and config.custom_ca_bundle is not None:
        return httpx.AsyncClient(verify=str(config.custom_ca_bundle))
    return httpx.AsyncClient()


@dataclass
class AppState:
    config: AppConfig
    store: Store
    cache: JsonCache
    http_client: httpx.AsyncClient
    latest_snapshot: dict[str, Any]
    inflight_usage_reports: dict[str, asyncio.Task[dict[str, Any]]]
    inflight_session_reports: dict[str, asyncio.Task[dict[str, Any] | None]]
    inflight_diagnostics_reports: dict[str, asyncio.Task[dict[str, Any]]]
    account_limit_update_lock: asyncio.Lock


def configure_runtime(config: AppConfig, application: FastAPI | None = None) -> AppState:
    global STATIC_DIR, SCHEMA_PATH, DEFAULT_DB, DEFAULT_TZ, SUMMARY_TIMES, VALKEY_URL, UPDATE_STATUS_PATH
    global UPDATE_CHECK_ENABLED, UPDATE_CHECK_INTERVAL_SECONDS, UPDATE_CHECK_TIMEOUT_SECONDS, UPDATE_CHECK_TAGS_URL, UPDATE_INSTALL_MODE
    global TODAY_CACHE_TTL_SECONDS, HISTORIC_CACHE_TTL_SECONDS, LATEST_SNAPSHOT_TTL_SECONDS, DEFAULT_DAYS_BACK
    global MAX_DATE_RANGE_DAYS, MAX_ACCOUNT_FILTERS, MAX_ALERT_LIMIT, MATERIALIZED_DAYS_BACK
    global AUTH_SNAPSHOT_SOURCE, FX_LIVE_ENABLED, FX_FALLBACK_RETRY_SECONDS, USAGE_AGGREGATE_CACHE_SCHEMA
    global CACHE_KEY_PREFIX, CACHE_MEMORY_FALLBACK_MODE, MONITOR_API_WORKERS, DEBUG_TIMING_ENABLED
    global store, cache, inflight_usage_reports, inflight_session_reports, inflight_diagnostics_reports
    global latest_snapshot, shared_http_client

    STATIC_DIR = config.static_dir
    SCHEMA_PATH = config.schema_path
    UPDATE_STATUS_PATH = config.update_status_path
    UPDATE_CHECK_ENABLED, UPDATE_CHECK_INTERVAL_SECONDS, UPDATE_CHECK_TIMEOUT_SECONDS, UPDATE_CHECK_TAGS_URL, UPDATE_INSTALL_MODE = (config.update_check_enabled, config.update_check_interval_seconds, config.update_check_timeout_seconds, config.update_check_tags_url, config.update_install_mode)
    DEFAULT_DB = config.db_path
    DEFAULT_TZ = config.timezone
    SUMMARY_TIMES = config.summary_times
    VALKEY_URL = config.valkey_url
    TODAY_CACHE_TTL_SECONDS = config.today_cache_ttl_seconds
    LATEST_SNAPSHOT_TTL_SECONDS = max(config.today_cache_ttl_seconds * 3, 180)
    HISTORIC_CACHE_TTL_SECONDS = config.historic_cache_ttl_seconds
    DEFAULT_DAYS_BACK = config.default_days_back
    MAX_DATE_RANGE_DAYS = config.max_date_range_days
    MAX_ACCOUNT_FILTERS = config.max_account_filters
    MAX_ALERT_LIMIT = config.max_alert_limit
    MATERIALIZED_DAYS_BACK = config.materialized_days_back
    AUTH_SNAPSHOT_SOURCE = config.auth_snapshot_source
    FX_LIVE_ENABLED = config.fx_live_enabled
    FX_FALLBACK_RETRY_SECONDS = config.fx_fallback_retry_seconds
    USAGE_AGGREGATE_CACHE_SCHEMA = config.usage_aggregate_cache_schema
    CACHE_KEY_PREFIX = config.cache_key_prefix
    CACHE_MEMORY_FALLBACK_MODE = config.cache_memory_fallback_mode
    MONITOR_API_WORKERS = config.monitor_api_workers
    DEBUG_TIMING_ENABLED = config.debug_timing_enabled

    timing_module.DEBUG_TIMING_ENABLED = config.debug_timing_enabled
    store_module.SCHEMA_PATH = config.schema_path
    store_module.DEFAULT_TZ = config.timezone
    store_module.AUTH_SNAPSHOT_SOURCE = config.auth_snapshot_source
    cache_module.CACHE_KEY_PREFIX = config.cache_key_prefix
    cache_keys_module.TODAY_CACHE_TTL_SECONDS = config.today_cache_ttl_seconds
    cache_keys_module.HISTORIC_CACHE_TTL_SECONDS = config.historic_cache_ttl_seconds
    dates_module.DEFAULT_TZ = config.timezone
    dates_module.MAX_DATE_RANGE_DAYS = config.max_date_range_days
    limits_module.DEFAULT_TZ = config.timezone
    accounts_module.AUTH_SNAPSHOT_SOURCE = config.auth_snapshot_source
    accounts_module.MAX_ACCOUNT_FILTERS = config.max_account_filters
    cache_module.CACHE_MEMORY_FALLBACK_MODE = config.cache_memory_fallback_mode
    cache_module.MONITOR_API_WORKERS = config.monitor_api_workers
    usage_module.DEFAULT_TZ = config.timezone
    usage_module.DEFAULT_DAYS_BACK = config.default_days_back
    usage_module.MATERIALIZED_DAYS_BACK = config.materialized_days_back
    usage_module.FX_LIVE_ENABLED = config.fx_live_enabled
    usage_module.FX_FALLBACK_RETRY_SECONDS = config.fx_fallback_retry_seconds
    usage_module.SCANNER_ENABLED = config.scanner_enabled
    usage_module.USAGE_AGGREGATE_CACHE_SCHEMA = config.usage_aggregate_cache_schema
    usage_module._pruned_usage_aggregate_schemas.clear()
    alerts_module.DEFAULT_TZ = config.timezone
    alerts_module.SUMMARY_TIMES = config.summary_times
    alerts_module.TODAY_CACHE_TTL_SECONDS = config.today_cache_ttl_seconds
    alerts_module.DEFAULT_DAYS_BACK = config.default_days_back

    store = Store(config.db_path)
    cache = JsonCache(
        config.valkey_url,
        config.cache_key_prefix,
        config.cache_memory_fallback_mode,
        config.monitor_api_workers,
    )
    inflight_usage_reports = {}
    inflight_session_reports = {}
    inflight_diagnostics_reports = {}
    latest_snapshot = {}
    shared_http_client = create_http_client(config)
    state = AppState(
        config,
        store,
        cache,
        shared_http_client,
        latest_snapshot,
        inflight_usage_reports,
        inflight_session_reports,
        inflight_diagnostics_reports,
        asyncio.Lock(),
    )
    if application is not None and not hasattr(application, "state"):
        application.state = SimpleNamespace()
    if application is not None:
        application.state.monitor = state
    return state


def active_http_client() -> Any:
    global shared_http_client
    if shared_http_client is None:
        shared_http_client = create_http_client(AppConfig.from_env())
    return shared_http_client


from .api_account_settings import account_attribution_report, cached_unknown_usage_totals, public_settings, validated_confirmed_account_limit
from .api_metadata import (
    changelog_section_has_items,
    non_empty_changelog_groups,
    parse_changelog_markdown,
    read_update_status,
)
from .api_scanner_runtime import publish_error_snapshot, run_scanner_followup, run_scanner_iteration, scanner_loop, sync_scanner_state
from .api_snapshot_state import (
    account_limit_cache_generation,
    account_limit_status_for_account,
    cache_account_limit_statuses,
    cached_account_limit_statuses,
    cached_account_limit_statuses_with_state,
    invalidate_derived_cache,
    local_snapshot_fallback,
    merge_account_limit_statuses,
    publish_latest_snapshot,
    refresh_snapshot_after_change,
    schedule_snapshot_refresh,
    seed_latest_account_limit_statuses,
    snapshot_with_cache_meta,
    warming_snapshot,
)
@asynccontextmanager
async def lifespan(application: FastAPI):
    state = getattr(application.state, "monitor", None)
    if state is None:
        state = configure_runtime(AppConfig.from_env(), application)
    task = asyncio.create_task(scanner_loop()) if state.config.scanner_enabled else None
    try:
        global latest_snapshot, requested_snapshot_generation
        settings = await state.store.settings()
        logger.info(
            "app_start version=%s scanner_enabled=%s pricing_mode=%s dashboard_mode=%s fx_live_enabled=%s",
            APP_VERSION,
            state.config.scanner_enabled,
            settings.get("pricing_mode") or state.config.pricing_mode,
            settings.get("dashboard_mode") or state.config.dashboard_mode,
            state.config.fx_live_enabled,
        )
        requested_snapshot_generation = await state.store.cache_generation()
        latest_snapshot = {
            "version": APP_VERSION,
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "status": "warming",
            "cache_generation": requested_snapshot_generation,
        }
        state.latest_snapshot = latest_snapshot
        yield
    finally:
        if task is not None:
            task.cancel()
            try:
                await task
            except asyncio.CancelledError:
                pass
        await state.http_client.aclose()
        await state.cache.aclose()


app = FastAPI(title="Codex Self-Hosted Web Monitor", lifespan=lifespan)
app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")


def create_app(config: AppConfig | None = None) -> FastAPI:
    configure_runtime(config or AppConfig.from_env(), app)
    return app


def sse_event(event: str, payload: dict[str, Any]) -> str:
    return f"event: {event}\ndata: {json.dumps(payload, sort_keys=True)}\n\n"


@app.middleware("http")
async def log_endpoint_call(request: Request, call_next):
    started = monotonic_time.perf_counter()
    status_code = 500
    try:
        response = await call_next(request)
        status_code = response.status_code
        return response
    finally:
        if DEBUG_TIMING_ENABLED:
            duration_ms = (monotonic_time.perf_counter() - started) * 1000
            logger.info(
                "endpoint method=%s path=%s status=%s duration_ms=%.1f",
                request.method,
                request.url.path,
                status_code,
                duration_ms,
            )


@app.get("/")
async def index() -> FileResponse:
    return FileResponse(STATIC_DIR / "index.html")


@app.get("/healthz", response_model=HealthResponse)
async def healthz() -> dict[str, Any]:
    generation = await store.cache_generation()
    snapshot = await cache.get(versioned_cache_key(generation, latest_snapshot_cache_key())) or local_snapshot_fallback()
    return {
        "ok": "error" not in snapshot,
        "version": APP_VERSION,
        "generated_at": snapshot.get("generated_at"),
        "error": snapshot.get("error"),
    }


@app.get("/api/changelog", response_model=ChangelogReport)
async def api_changelog(limit: int = 5) -> dict[str, Any]:
    if limit < 1 or limit > 20:
        raise HTTPException(status_code=400, detail="limit must be between 1 and 20")
    if not CHANGELOG_PATH.exists():
        raise HTTPException(status_code=404, detail="CHANGELOG.md not found")
    releases, unreleased = parse_changelog_markdown(CHANGELOG_PATH.read_text(encoding="utf-8"), limit)
    return {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "source": CHANGELOG_PATH.name,
        "releases": releases,
        "unreleased": unreleased,
    }


@app.get("/api/update-status", response_model=UpdateStatusResponse)
async def api_update_status() -> dict[str, Any]:
    return read_update_status(UPDATE_STATUS_PATH)


@app.get("/api/snapshot", response_model=SnapshotResponse)
async def api_snapshot() -> dict[str, Any]:
    generation = await store.cache_generation()
    today = now_local().date()
    cached = await cache.get(versioned_cache_key(generation, snapshot_cache_key(today)))
    if cached:
        return await snapshot_with_cache_meta(cached, TODAY_CACHE_TTL_SECONDS, generation)
    latest_cached = await cache.get(versioned_cache_key(generation, latest_snapshot_cache_key()))
    if latest_cached:
        return await snapshot_with_cache_meta(latest_cached, LATEST_SNAPSHOT_TTL_SECONDS, generation)
    snapshot = warming_snapshot()
    snapshot["cache_generation"] = generation
    snapshot["cache"] = {
        "response": response_cache_meta(False, LATEST_SNAPSHOT_TTL_SECONDS),
        "backend": await cache.status(),
        "generation": generation,
    }
    return snapshot


@app.get("/api/events")
async def api_events(request: Request) -> StreamingResponse:
    async def stream():
        last_generated_at = ""
        while True:
            if await request.is_disconnected():
                break
            generation = await store.cache_generation()
            snapshot = await cache.get(versioned_cache_key(generation, latest_snapshot_cache_key())) or local_snapshot_fallback()
            generated_at = str(snapshot.get("generated_at") or "")
            if generated_at and generated_at != last_generated_at:
                last_generated_at = generated_at
                yield sse_event(
                    "dashboard_update",
                    {
                        "type": "dashboard_update",
                        "generated_at": generated_at,
                        "reason": snapshot.get("update_reason"),
                    },
                )
            else:
                yield ": keepalive\n\n"
            await asyncio.sleep(15)

    return StreamingResponse(stream(), media_type="text/event-stream")


def parse_api_window(start_at: str | None, end_at: str | None) -> tuple[datetime, datetime]:
    local_now = now_local()
    default_start = datetime.combine((local_now - timedelta(days=DEFAULT_DAYS_BACK)).date(), datetime.min.time(), local_now.tzinfo)
    default_end = datetime.combine(local_now.date() + timedelta(days=1), datetime.min.time(), local_now.tzinfo)
    start = parse_api_datetime(start_at, default_start, "start_at")
    end = parse_api_datetime(end_at, default_end, "end_at")
    validate_datetime_range(start, end)
    return start, end


@app.get("/api/summary", response_model=UsageReport)
async def api_summary(
    period: str = "today",
    date_from: str | None = None,
    date_to: str | None = None,
    start_at: str | None = None,
    end_at: str | None = None,
    accounts: str | None = None,
) -> dict[str, Any]:
    if start_at or end_at:
        start, end = parse_api_window(start_at, end_at)
        return await usage_report_for_window(start, end, parse_accounts_param(accounts))
    today = now_local().date()
    if date_from or date_to:
        start = parse_api_day(date_from, today - timedelta(days=DEFAULT_DAYS_BACK), "date_from")
        end = parse_api_day(date_to, today, "date_to")
        validate_date_range(start, end)
    else:
        try:
            start, end = period_bounds(period, today)
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
    return await usage_report(start, end, parse_accounts_param(accounts))


@app.get("/api/days", response_model=DaysReport)
async def api_days(
    date_from: str | None = None,
    date_to: str | None = None,
    start_at: str | None = None,
    end_at: str | None = None,
    accounts: str | None = None,
) -> dict[str, Any]:
    if start_at or end_at:
        start, end = parse_api_window(start_at, end_at)
        return await days_report_for_window(start, end, parse_accounts_param(accounts))
    today = now_local().date()
    start = parse_api_day(date_from, today - timedelta(days=DEFAULT_DAYS_BACK), "date_from")
    end = parse_api_day(date_to, today, "date_to")
    validate_date_range(start, end)
    return await days_report(start, end, parse_accounts_param(accounts))


@app.get("/api/sessions", response_model=SessionHistoryReport)
async def api_sessions(
    date_from: str | None = None,
    date_to: str | None = None,
    start_at: str | None = None,
    end_at: str | None = None,
    accounts: str | None = None,
) -> dict[str, Any]:
    if start_at or end_at:
        start, end = parse_api_window(start_at, end_at)
        return await session_history_report_for_window(start, end, parse_accounts_param(accounts))
    today = now_local().date()
    start = parse_api_day(date_from, today - timedelta(days=DEFAULT_DAYS_BACK), "date_from")
    end = parse_api_day(date_to, today, "date_to")
    validate_date_range(start, end)
    return await session_history_report(start, end, parse_accounts_param(accounts))


@app.get("/api/sessions/{session_id}", response_model=SessionDetail)
async def api_session_detail(
    session_id: str,
    date_from: str | None = None,
    date_to: str | None = None,
    start_at: str | None = None,
    end_at: str | None = None,
    accounts: str | None = None,
) -> dict[str, Any]:
    if start_at or end_at:
        start, end = parse_api_window(start_at, end_at)
        report = await session_detail_report_for_window(start, end, session_id, parse_accounts_param(accounts))
        if report is None:
            raise HTTPException(status_code=404, detail=f"session not found: {session_id}")
        return report
    today = now_local().date()
    start = parse_api_day(date_from, today - timedelta(days=DEFAULT_DAYS_BACK), "date_from")
    end = parse_api_day(date_to, today, "date_to")
    validate_date_range(start, end)
    report = await session_detail_report(start, end, session_id, parse_accounts_param(accounts))
    if report is None:
        raise HTTPException(status_code=404, detail=f"session not found: {session_id}")
    return report


@app.get("/api/usage-diagnostics", response_model=UsageDiagnosticsReport)
async def api_usage_diagnostics(date_from: str | None = None, date_to: str | None = None, start_at: str | None = None, end_at: str | None = None, accounts: str | None = None) -> dict[str, Any]:
    if start_at or end_at:
        start, end = parse_api_window(start_at, end_at)
        return await usage_diagnostics_report_for_window(start, end, parse_accounts_param(accounts))
    today = now_local().date()
    start = parse_api_day(date_from, today - timedelta(days=DEFAULT_DAYS_BACK), "date_from")
    end = parse_api_day(date_to, today, "date_to")
    validate_date_range(start, end)
    return await usage_diagnostics_report(start, end, parse_accounts_param(accounts))


@app.get("/api/accounts", response_model=AccountsReport)
async def api_accounts() -> dict[str, Any]:
    snapshots = await store.auth_snapshots(limit=1000)
    today = now_local().date()
    start = today - timedelta(days=DEFAULT_DAYS_BACK)
    report = await usage_report(start, today)
    accounts = merge_usage_account_options(account_options_from_snapshots(snapshots), report_account_labels(report, snapshots))
    attribution = await account_attribution_report(snapshots)
    return {"accounts": accounts, "snapshots": snapshots, "attribution": attribution, "auto_account_limit_defaults": auto_account_limit_defaults()}


@app.post("/api/auth-snapshots", response_model=AuthSnapshotResult)
async def api_create_auth_snapshot(payload: AuthSnapshotCreate) -> dict[str, Any]:
    data = payload.model_dump(exclude_unset=True)
    observed_at = data.get("observed_at") or datetime.now(timezone.utc).isoformat()
    try:
        parse_snapshot_time(str(observed_at))
    except ValueError as exc:
        raise HTTPException(status_code=400, detail="observed_at must be an ISO timestamp") from exc
    snapshot = {
        "observed_at": str(observed_at),
        "account_id": data.get("account_id"),
        "email": str(data.get("email") or "").strip().lower() or None,
        "name": data.get("name"),
        "source": data.get("source") or "manual",
    }
    if not snapshot["account_id"] and not snapshot["email"]:
        raise HTTPException(status_code=400, detail="account_id or email is required")
    inserted = await store.record_auth_snapshot(snapshot)
    if inserted:
        await invalidate_derived_cache("manual_auth_snapshot")
    ensured = await ensure_default_account_limits_from_snapshots([snapshot])
    if any(limit.get("_inserted") for limit in ensured):
        await invalidate_derived_cache("default_account_limits")
    return {"inserted": inserted, "snapshot": snapshot}


@app.get("/api/account-limits", response_model=AccountLimitsReport)
async def api_account_limits() -> dict[str, Any]:
    limits = await store.account_limits(enabled_only=False)
    statuses, status_state = await cached_account_limit_statuses_with_state(limits, live_fallback=False)
    return {"limits": limits, "statuses": statuses, "status_state": status_state}


@app.put("/api/account-limits", response_model=AccountLimitPutResult)
async def api_put_account_limit(payload: AccountLimitUpdate) -> dict[str, Any]:
    state = getattr(app.state, "monitor", None)
    update_lock = state.account_limit_update_lock if state is not None else asyncio.Lock()
    request_started = monotonic_time.perf_counter()
    async with update_lock:
        seed_generation = await account_limit_cache_generation()
        cached_statuses = await cached_account_limit_statuses(generation=seed_generation, live_fallback=False)
        validation_started = monotonic_time.perf_counter()
        validated = await validated_confirmed_account_limit(payload.model_dump(exclude_unset=True))
        validation_ms = (monotonic_time.perf_counter() - validation_started) * 1000
        db_started = monotonic_time.perf_counter()
        limit = await store.upsert_account_limit(validated)
        db_write_ms = (monotonic_time.perf_counter() - db_started) * 1000
        invalidation_started = monotonic_time.perf_counter()
        generation = await invalidate_derived_cache("account_limit")
        account_generation = await account_limit_cache_generation()
        generation_bump_ms = (monotonic_time.perf_counter() - invalidation_started) * 1000
        status_seed_started = monotonic_time.perf_counter()
        status = None
        if cached_statuses and account_generation == (seed_generation + 1):
            seeded_statuses = merge_account_limit_statuses(cached_statuses, str(limit["account"]).strip().lower(), None)
            await cache_account_limit_statuses(seeded_statuses, account_generation, "refreshing")
            seed_latest_account_limit_statuses(seeded_statuses, generation)
        status_build_ms = (monotonic_time.perf_counter() - status_seed_started) * 1000
        schedule_snapshot_refresh("account_limit", generation)
        total_ms = (monotonic_time.perf_counter() - request_started) * 1000
        logger.info(
            "account_limit_save_timing validation_ms=%.1f db_write_ms=%.1f generation_bump_ms=%.1f status_seed_ms=%.1f total_ms=%.1f",
            validation_ms,
            db_write_ms,
            generation_bump_ms,
            status_build_ms,
            total_ms,
        )
        return {"limit": limit, "status": status, "status_state": "refreshing"}


@app.get("/api/settings", response_model=dict[str, str])
async def api_get_settings() -> dict[str, str]:
    return public_settings(await store.settings())


@app.get("/api/rate-card", response_model=RateCard)
async def api_rate_card() -> dict[str, Any]:
    return codex_rate_card()


@app.put("/api/settings", response_model=dict[str, str])
async def api_put_settings(updates: SettingsUpdate) -> dict[str, str]:
    data = updates.model_dump(exclude_unset=True)
    data.update(updates.model_extra)
    if "unknown_account_mapping" in data:
        snapshots = await store.auth_snapshots(limit=1000)
        try:
            data["unknown_account_mapping"] = validate_unknown_account_mapping(data.get("unknown_account_mapping"), snapshots)
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
    threshold_keys_changed = bool(SESSION_SIGNAL_THRESHOLD_KEYS.intersection(data))
    previous_settings = await store.settings() if ("unknown_account_mapping" in data or threshold_keys_changed) else {}
    saved = await store.update_settings(validate_settings_updates(data))
    if "unknown_account_mapping" in data and previous_settings.get("unknown_account_mapping", "") != saved.get("unknown_account_mapping", ""):
        await invalidate_derived_cache("unknown_account_mapping")
    elif threshold_keys_changed and any(previous_settings.get(key) != saved.get(key) for key in SESSION_SIGNAL_THRESHOLD_KEYS):
        await invalidate_derived_cache("session_signal_thresholds")
    return public_settings(saved)


@app.get("/api/alerts", response_model=list[AlertResponse])
async def api_alerts(limit: int = 50) -> list[dict[str, Any]]:
    if limit < 1 or limit > MAX_ALERT_LIMIT:
        raise HTTPException(status_code=400, detail=f"limit must be between 1 and {MAX_ALERT_LIMIT}")
    return await store.alerts(limit)


@app.post("/api/test-webhook", response_model=WebhookResult)
async def api_test_webhook() -> dict[str, Any]:
    settings = await store.settings()
    payload = {
        "type": "test",
        "message": "Codex Self-Hosted Web Monitor webhook test",
        "dashboard_url": settings.get("dashboard_url", "http://127.0.0.1:8787"),
        "created_at": datetime.now(timezone.utc).isoformat(),
    }
    return await send_webhook(settings, payload)
