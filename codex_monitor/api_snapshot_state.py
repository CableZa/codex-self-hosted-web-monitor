from __future__ import annotations

import asyncio
import json
from datetime import datetime, timezone
from typing import Any

from . import api_app as app_module
from .api_cache_keys import account_limit_statuses_cache_key, latest_snapshot_cache_key, response_cache_meta, snapshot_cache_key, versioned_cache_key
from .api_dates import now_local
from .api_alerts import account_limit_status_for_limit
from .api_refs import cache, inflight_diagnostics_reports, inflight_session_reports, inflight_usage_reports, store
from .api_timing import logger
from .api_usage import USAGE_CACHE_GENERATION_KEY, snapshot_has_usage_activity
from .version import APP_VERSION

ACCOUNT_LIMIT_GENERATION_KEY = "account_limit_generation"


async def publish_latest_snapshot(snapshot: dict[str, Any], expected_generation: int | None = None) -> bool:
    current_generation = await store.cache_generation()
    app_module.requested_snapshot_generation = current_generation
    generation = current_generation if expected_generation is None else expected_generation
    if expected_generation is not None and current_generation != expected_generation:
        logger.info(
            "snapshot_publish_skipped reason=stale_generation expected_generation=%s requested_generation=%s",
            expected_generation,
            current_generation,
        )
        return False
    snapshot = {**snapshot, "cache_generation": generation}
    app_module.latest_snapshot = snapshot
    state = getattr(app_module.app.state, "monitor", None)
    if state is not None:
        state.latest_snapshot = snapshot
    await cache.set(versioned_cache_key(generation, latest_snapshot_cache_key()), snapshot, app_module.LATEST_SNAPSHOT_TTL_SECONDS)
    today = app_module.now_local().date()
    if snapshot_has_usage_activity(snapshot):
        await cache.set(versioned_cache_key(generation, snapshot_cache_key(today)), snapshot, app_module.TODAY_CACHE_TTL_SECONDS)
    if isinstance(snapshot.get("account_limits"), list):
        await cache_account_limit_statuses(snapshot["account_limits"], await account_limit_cache_generation())
    return True


def warming_snapshot() -> dict[str, Any]:
    return {
        "version": APP_VERSION,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "status": "warming",
    }


def local_snapshot_fallback() -> dict[str, Any]:
    if app_module.latest_snapshot.get("status") == "warming":
        return app_module.latest_snapshot
    return warming_snapshot()


def merge_account_limit_statuses(
    existing_statuses: list[dict[str, Any]],
    account: str,
    status: dict[str, Any] | None,
) -> list[dict[str, Any]]:
    merged = [item for item in existing_statuses if str(item.get("account") or "").strip().lower() != account]
    if status is not None:
        merged.append(status)
    return sorted(merged, key=lambda item: str(item.get("account") or ""))


async def account_limit_cache_generation(generation: int | None = None) -> int:
    if generation is not None:
        return generation
    return await store.setting_generation(ACCOUNT_LIMIT_GENERATION_KEY)


def account_limit_status_for_account(statuses: list[dict[str, Any]], account: str) -> dict[str, Any] | None:
    normalized = account.strip().lower()
    for status in statuses:
        if str(status.get("account") or "").strip().lower() == normalized:
            return status
    return None


async def cache_account_limit_statuses(
    statuses: list[dict[str, Any]],
    generation: int,
    status_state: str = "ready",
) -> None:
    payload = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "generation": generation,
        "status_state": status_state,
        "statuses": statuses,
    }
    await cache.set(
        versioned_cache_key(generation, account_limit_statuses_cache_key()),
        payload,
        app_module.ACCOUNT_LIMIT_STATUS_TTL_SECONDS,
    )


def seed_latest_account_limit_statuses(
    statuses: list[dict[str, Any]],
    expected_generation: int | None = None,
) -> bool:
    if expected_generation is not None and app_module.requested_snapshot_generation != expected_generation:
        logger.info(
            "account_limit_seed_skipped expected_generation=%s requested_generation=%s",
            expected_generation,
            app_module.requested_snapshot_generation,
        )
        return False
    app_module.latest_snapshot = {**app_module.latest_snapshot, "account_limits": statuses}
    state = getattr(app_module.app.state, "monitor", None)
    if state is not None:
        state.latest_snapshot = app_module.latest_snapshot
    return True


async def cached_account_limit_statuses(
    limits: list[dict[str, Any]] | None = None,
    *,
    generation: int | None = None,
    live_fallback: bool = True,
) -> list[dict[str, Any]]:
    statuses, _state = await cached_account_limit_statuses_with_state(
        limits,
        generation=generation,
        live_fallback=live_fallback,
    )
    return statuses


async def cached_account_limit_statuses_with_state(
    limits: list[dict[str, Any]] | None = None,
    *,
    generation: int | None = None,
    live_fallback: bool = False,
) -> tuple[list[dict[str, Any]], str]:
    active_generation = await account_limit_cache_generation(generation)
    cached_statuses = await cache.get(versioned_cache_key(active_generation, account_limit_statuses_cache_key()))
    if isinstance(cached_statuses, dict) and isinstance(cached_statuses.get("statuses"), list):
        return cached_statuses["statuses"], str(cached_statuses.get("status_state") or "ready")
    cached = await cache.get(versioned_cache_key(active_generation, latest_snapshot_cache_key()))
    if isinstance(cached, dict) and isinstance(cached.get("account_limits"), list):
        return cached["account_limits"], "ready"
    if isinstance(app_module.latest_snapshot.get("account_limits"), list):
        return app_module.latest_snapshot["account_limits"], "warming"
    if active_generation > 1:
        stale_statuses = await cache.get(versioned_cache_key(active_generation - 1, account_limit_statuses_cache_key()))
        if isinstance(stale_statuses, dict) and isinstance(stale_statuses.get("statuses"), list):
            return stale_statuses["statuses"], "warming"
    if not live_fallback:
        return [], "warming"
    live_limits = limits if limits is not None else await store.account_limits(enabled_only=False)
    enabled_limits = [limit for limit in live_limits if bool(limit.get("enabled", 1))]
    statuses = [await account_limit_status_for_limit(limit) for limit in enabled_limits]
    return statuses, "ready"


async def refresh_snapshot_after_change(reason: str, expected_generation: int) -> None:
    try:
        current_generation = await store.cache_generation()
        if current_generation != expected_generation:
            logger.info(
                "snapshot_refresh_after_change_skipped reason=%s expected_generation=%s current_generation=%s",
                reason,
                expected_generation,
                current_generation,
            )
            return
        snapshot = await app_module.build_snapshot()
        snapshot["update_reason"] = reason
        await app_module.publish_latest_snapshot(snapshot, expected_generation)
    except Exception:
        logger.exception("snapshot_refresh_after_change_failed reason=%s", reason)


def schedule_snapshot_refresh(reason: str, expected_generation: int) -> None:
    asyncio.create_task(app_module.refresh_snapshot_after_change(reason, expected_generation))


async def invalidate_derived_cache(reason: str) -> int:
    generation = await store.bump_cache_generation(reason)
    app_module.requested_snapshot_generation = generation
    normalized_reason = reason.lower()
    if any(item in normalized_reason for item in ("auth_snapshot", "unknown_account_mapping", "session_signal_thresholds")):
        await store.bump_setting_generation(USAGE_CACHE_GENERATION_KEY, reason)
        inflight_usage_reports.clear()
        inflight_session_reports.clear()
        inflight_diagnostics_reports.clear()
    if any(item in normalized_reason for item in ("account_limit", "auth_snapshot", "unknown_account_mapping")):
        await store.bump_setting_generation(ACCOUNT_LIMIT_GENERATION_KEY, reason)
    app_module.latest_snapshot = app_module.warming_snapshot()
    app_module.latest_snapshot["cache_generation"] = generation
    app_module.latest_snapshot["update_reason"] = reason
    state = getattr(app_module.app.state, "monitor", None)
    if state is not None:
        state.latest_snapshot = app_module.latest_snapshot
    logger.info("derived_cache_invalidated reason=%s generation=%s", reason, generation)
    return generation


async def snapshot_with_cache_meta(snapshot: dict[str, Any], ttl_seconds: int, generation: int) -> dict[str, Any]:
    result = json.loads(json.dumps(snapshot))
    result["cache"] = {
        "response": response_cache_meta(True, ttl_seconds),
        "backend": await cache.status(),
        "generation": generation,
    }
    return result
