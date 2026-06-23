from __future__ import annotations

import asyncio
import time
from datetime import datetime, timedelta, timezone
from typing import Any

from . import api_app as app_module
from .api_timing import logger
from .update_status import checking_failed_status, fresh_updating_status, http_update_state, write_status
from .version import APP_VERSION

last_update_check_monotonic = 0.0


async def sync_scanner_state() -> list[str]:
    auth_snapshot = await app_module.record_current_auth_snapshot()
    snapshots = await app_module.store.auth_snapshots(limit=1000)
    ensured = await app_module.ensure_default_account_limits_from_snapshots(snapshots)
    reasons: list[str] = []
    if auth_snapshot and auth_snapshot.get("_inserted"):
        reasons.append("auth_snapshot")
    if any(limit.get("_inserted") for limit in ensured):
        reasons.append("default_account_limits")
    if reasons:
        await app_module.invalidate_derived_cache("+".join(reasons))
    return reasons


async def publish_error_snapshot(exc: Exception) -> None:
    try:
        await app_module.publish_latest_snapshot(
            {"version": APP_VERSION, "error": str(exc), "generated_at": datetime.now(timezone.utc).isoformat()}
        )
    except Exception:  # pragma: no cover
        logger.exception("scanner_error_publish_failed")


async def run_scanner_followup(snapshot: dict[str, Any]) -> None:
    snapshot_now = app_module.now_local()
    today = snapshot_now.date()
    await app_module.days_report(today - timedelta(days=app_module.DEFAULT_DAYS_BACK), today)
    await app_module.maybe_send_summaries(snapshot)
    await app_module.materialize_common_ranges(snapshot_now)


async def run_scanner_iteration() -> None:
    try:
        await app_module.sync_scanner_state()
        expected_generation = await app_module.store.cache_generation()
        snapshot = await app_module.build_snapshot()
        await app_module.publish_latest_snapshot(snapshot, expected_generation)
    except Exception as exc:  # pragma: no cover
        logger.exception("scanner_loop_failed")
        await app_module.publish_error_snapshot(exc)
        return

    try:
        await app_module.run_scanner_followup(snapshot)
    except Exception:  # pragma: no cover
        logger.exception("scanner_followup_failed")


async def maybe_check_for_updates() -> None:
    global last_update_check_monotonic
    if not app_module.UPDATE_CHECK_ENABLED:
        return
    now = time.monotonic()
    interval = max(app_module.UPDATE_CHECK_INTERVAL_SECONDS, 60)
    if last_update_check_monotonic and now - last_update_check_monotonic < interval:
        return
    last_update_check_monotonic = now

    status_path = app_module.UPDATE_STATUS_PATH
    if fresh_updating_status(status_path, max(interval, 3600)):
        return

    install_mode = app_module.UPDATE_INSTALL_MODE
    try:
        status = await http_update_state(
            http_client=app_module.active_http_client(),
            tags_url=app_module.UPDATE_CHECK_TAGS_URL,
            current_version=APP_VERSION,
            install_mode=install_mode,
            timeout_seconds=app_module.UPDATE_CHECK_TIMEOUT_SECONDS,
        )
    except Exception as exc:  # pragma: no cover
        logger.warning("update_check_failed error=%s", exc)
        status = checking_failed_status(
            current_version=APP_VERSION,
            running_version=APP_VERSION,
            install_mode=install_mode,
            check_mode="builtin_http",
            source_url=app_module.UPDATE_CHECK_TAGS_URL,
            error=exc,
        )
    try:
        write_status(status_path, status)
    except Exception as exc:  # pragma: no cover
        logger.warning("update_status_write_failed path=%s error=%s", status_path, exc)


async def scanner_loop() -> None:
    while True:
        await app_module.run_scanner_iteration()
        await maybe_check_for_updates()
        await asyncio.sleep(60)
