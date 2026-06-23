from __future__ import annotations

import os
from dataclasses import dataclass
from datetime import time
from pathlib import Path


def bool_env(name: str, default: bool) -> bool:
    value = os.environ.get(name)
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


@dataclass(frozen=True)
class AppConfig:
    script_dir: Path
    static_dir: Path
    schema_path: Path
    db_path: Path
    timezone: str
    summary_times: tuple[time, ...]
    valkey_url: str
    today_cache_ttl_seconds: int
    historic_cache_ttl_seconds: int
    default_days_back: int
    max_date_range_days: int
    max_account_filters: int
    max_alert_limit: int
    materialized_days_back: tuple[int, ...]
    log_level: str
    auth_snapshot_source: str
    pricing_mode: str
    dashboard_mode: str
    fx_live_enabled: bool
    fx_fallback_retry_seconds: int
    custom_ca_bundle: Path | None
    usage_aggregate_cache_schema: str
    cache_key_prefix: str
    cache_memory_fallback_mode: str
    monitor_api_workers: int
    update_status_path: Path
    update_check_enabled: bool
    update_check_interval_seconds: int
    update_check_timeout_seconds: int
    update_check_tags_url: str
    update_install_mode: str
    debug_timing_enabled: bool
    scanner_enabled: bool

    @classmethod
    def from_env(cls) -> "AppConfig":
        script_dir = Path(__file__).resolve().parent.parent
        return cls(
            script_dir=script_dir,
            static_dir=script_dir / "static",
            schema_path=script_dir / "sql" / "schema.sql",
            db_path=Path(os.environ.get("MONITOR_DB", script_dir / "monitor.sqlite3")),
            timezone=os.environ.get("TIMEZONE", "UTC"),
            summary_times=(time(10, 0), time(15, 0)),
            valkey_url=os.environ.get("VALKEY_URL", "redis://127.0.0.1:6379/0"),
            today_cache_ttl_seconds=int(os.environ.get("TODAY_CACHE_TTL_SECONDS", "90")),
            historic_cache_ttl_seconds=int(os.environ.get("HISTORIC_CACHE_TTL_SECONDS", str(7 * 24 * 60 * 60))),
            default_days_back=int(os.environ.get("DEFAULT_DAYS_BACK", "30")),
            max_date_range_days=int(os.environ.get("MAX_DATE_RANGE_DAYS", "366")),
            max_account_filters=int(os.environ.get("MAX_ACCOUNT_FILTERS", "50")),
            max_alert_limit=int(os.environ.get("MAX_ALERT_LIMIT", "200")),
            materialized_days_back=(7, 30, 60, 90),
            log_level=os.environ.get("LOG_LEVEL", "INFO").upper(),
            auth_snapshot_source="codex_auth",
            pricing_mode=os.environ.get("PRICING_MODE", "credits"),
            dashboard_mode=os.environ.get("DASHBOARD_MODE", "full"),
            fx_live_enabled=bool_env("FX_LIVE_ENABLED", False),
            fx_fallback_retry_seconds=int(os.environ.get("FX_FALLBACK_RETRY_SECONDS", "3600")),
            custom_ca_bundle=Path(value) if (value := os.environ.get("CUSTOM_CA_BUNDLE", "").strip()) else None,
            usage_aggregate_cache_schema="v4",
            cache_key_prefix=os.environ.get("CACHE_KEY_PREFIX", "codex-monitor"),
            cache_memory_fallback_mode=os.environ.get("CACHE_MEMORY_FALLBACK_MODE", "single-worker"),
            monitor_api_workers=int(os.environ.get("MONITOR_API_WORKERS", "1")),
            update_status_path=Path(os.environ.get("UPDATE_STATUS_PATH", script_dir / "runtime" / "update-status.json")),
            update_check_enabled=bool_env("UPDATE_CHECK_ENABLED", True),
            update_check_interval_seconds=int(os.environ.get("UPDATE_CHECK_INTERVAL_SECONDS", "21600")),
            update_check_timeout_seconds=int(os.environ.get("UPDATE_CHECK_TIMEOUT_SECONDS", "8")),
            update_check_tags_url=os.environ.get(
                "UPDATE_CHECK_TAGS_URL",
                "https://api.github.com/repos/CableZa/codex-self-hosted-web-monitor/tags?per_page=100",
            ),
            update_install_mode=os.environ.get("UPDATE_INSTALL_MODE", "auto"),
            debug_timing_enabled=bool_env("DEBUG_TIMING_ENABLED", True),
            scanner_enabled=bool_env("SCANNER_ENABLED", True),
        )
