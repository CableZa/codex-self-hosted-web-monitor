from __future__ import annotations

import asyncio
from datetime import datetime, timedelta, timezone
from typing import Any

from . import api_app as app_module
from .api_timing import logger
from .version import APP_VERSION


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


async def scanner_loop() -> None:
    while True:
        await app_module.run_scanner_iteration()
        await asyncio.sleep(60)
