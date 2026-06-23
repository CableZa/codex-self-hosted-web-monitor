from __future__ import annotations

import asyncio
import json
import os
import sqlite3
import time
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any, Callable, TypeVar

from .api_dates import DEFAULT_TZ
from .api_http import validate_outbound_url
from .api_timing import logger, timed_dependency
from .session_signals import SESSION_SIGNAL_THRESHOLD_DEFAULTS, SESSION_SIGNAL_THRESHOLD_KEYS

SCRIPT_DIR = Path(__file__).resolve().parent.parent
SCHEMA_PATH = SCRIPT_DIR / "sql" / "schema.sql"
DEFAULT_DB = Path(os.environ.get("MONITOR_DB", SCRIPT_DIR / "monitor.sqlite3"))
AUTH_SNAPSHOT_SOURCE = "codex_auth"
DbResult = TypeVar("DbResult")
SQLITE_LOCK_RETRY_ATTEMPTS = 8
SQLITE_LOCK_RETRY_DELAY_SECONDS = 0.05
SQLITE_BUSY_TIMEOUT_MS = 30000
SQLITE_INTERACTIVE_BUSY_TIMEOUT_MS = int(os.environ.get("SQLITE_INTERACTIVE_BUSY_TIMEOUT_MS", "1000"))
SQLITE_INTERACTIVE_RETRY_ATTEMPTS = int(os.environ.get("SQLITE_INTERACTIVE_RETRY_ATTEMPTS", "3"))


class Store:
    def __init__(self, path: Path = DEFAULT_DB):
        self.path = path
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.conn = sqlite3.connect(self.path, check_same_thread=False, timeout=30)
        self.conn.row_factory = sqlite3.Row
        self.lock = asyncio.Lock()
        self.configure_connection()
        self.init_schema()

    async def _run_db(
        self,
        operation: Callable[[], DbResult],
        *,
        attempts: int = SQLITE_LOCK_RETRY_ATTEMPTS,
        delay_seconds: float = SQLITE_LOCK_RETRY_DELAY_SECONDS,
        busy_timeout_ms: int | None = None,
    ) -> DbResult:
        async with self.lock:
            task = asyncio.create_task(
                asyncio.to_thread(
                    self._run_db_operation,
                    operation,
                    attempts,
                    delay_seconds,
                    busy_timeout_ms,
                )
            )
            try:
                return await asyncio.shield(task)
            except asyncio.CancelledError:
                while not task.done():
                    try:
                        await asyncio.shield(task)
                    except asyncio.CancelledError:
                        continue
                if not task.cancelled():
                    task.exception()
                raise

    @staticmethod
    def _is_locked_error(exc: sqlite3.OperationalError) -> bool:
        return "locked" in str(exc).lower()

    def _run_db_operation(
        self,
        operation: Callable[[], DbResult],
        attempts: int,
        delay_seconds: float,
        busy_timeout_ms: int | None,
    ) -> DbResult:
        original_busy_timeout = SQLITE_BUSY_TIMEOUT_MS
        if busy_timeout_ms is not None:
            try:
                self.conn.execute(f"pragma busy_timeout = {int(busy_timeout_ms)}")
            except sqlite3.DatabaseError:
                pass
        try:
            for attempt in range(1, attempts + 1):
                try:
                    return operation()
                except sqlite3.OperationalError as exc:
                    try:
                        self.conn.rollback()
                    except sqlite3.DatabaseError:
                        pass
                    if not self._is_locked_error(exc) or attempt == attempts:
                        raise
                    retry_delay = delay_seconds * attempt
                    logger.warning(
                        "sqlite_operation_locked path=%s attempt=%s delay_seconds=%.2f",
                        self.path,
                        attempt,
                        retry_delay,
                    )
                    time.sleep(retry_delay)
                except sqlite3.DatabaseError:
                    try:
                        self.conn.rollback()
                    except sqlite3.DatabaseError:
                        pass
                    raise
            raise RuntimeError("sqlite retry loop exited unexpectedly")
        finally:
            if busy_timeout_ms is not None:
                try:
                    self.conn.execute(f"pragma busy_timeout = {int(original_busy_timeout)}")
                except sqlite3.DatabaseError:
                    pass

    async def _run_interactive_db(self, operation: Callable[[], DbResult]) -> DbResult:
        return await self._run_db(
            operation,
            attempts=max(SQLITE_INTERACTIVE_RETRY_ATTEMPTS, 1),
            delay_seconds=SQLITE_LOCK_RETRY_DELAY_SECONDS,
            busy_timeout_ms=max(SQLITE_INTERACTIVE_BUSY_TIMEOUT_MS, 0),
        )

    def configure_connection(self) -> None:
        self.conn.execute(f"pragma busy_timeout = {SQLITE_BUSY_TIMEOUT_MS}")
        try:
            self.conn.execute("pragma journal_mode = wal")
        except sqlite3.DatabaseError as exc:
            logger.warning("sqlite_wal_unavailable path=%s reason=%s", self.path, exc)

    def init_schema(self) -> None:
        for attempt in range(1, 31):
            try:
                self._init_schema_once()
                return
            except sqlite3.OperationalError as exc:
                message = str(exc).lower()
                try:
                    self.conn.rollback()
                except sqlite3.DatabaseError:
                    pass
                if "locked" not in message or attempt == 30:
                    raise
                logger.warning("sqlite_schema_init_locked path=%s attempt=%s", self.path, attempt)
                time.sleep(0.2)

    def _init_schema_once(self) -> None:
        self.conn.executescript(SCHEMA_PATH.read_text(encoding="utf-8"))
        self.conn.execute(
            "insert or ignore into schema_migrations(version, applied_at) values(?, ?)",
            (1, datetime.now(timezone.utc).isoformat()),
        )
        self.ensure_alert_credit_columns()
        self.ensure_account_limit_reset_time_column()
        webhook_url = os.environ.get("WEBHOOK_URL", "")
        defaults = {
            "daily_budget_zar": "0",
            "weekly_budget_zar": "0",
            "monthly_budget_zar": "0",
            "daily_budget_credits": os.environ.get("DAILY_BUDGET_CREDITS", "100"),
            "weekly_budget_credits": os.environ.get("WEEKLY_BUDGET_CREDITS", "700"),
            "monthly_budget_credits": os.environ.get("MONTHLY_BUDGET_CREDITS", "3000"),
            "pricing_mode": os.environ.get("PRICING_MODE", "credits"),
            "account_credit_limit_migration_done": "false",
            "usd_zar_fallback_rate": os.environ.get("USD_ZAR_FALLBACK_RATE", "18.50"),
            "webhook_url": webhook_url,
            "dashboard_url": os.environ.get("DASHBOARD_URL", "http://127.0.0.1:8787"),
            "dashboard_mode": os.environ.get("DASHBOARD_MODE", "full"),
            "ui_theme": os.environ.get("UI_THEME", "catppuccin"),
            "unknown_account_mapping": os.environ.get("UNKNOWN_ACCOUNT_MAPPING", ""),
            "cache_generation": "1",
            **SESSION_SIGNAL_THRESHOLD_DEFAULTS,
        }
        for key, value in defaults.items():
            self.conn.execute(
                "insert or ignore into settings(key, value) values(?, ?)",
                (key, value),
            )
        self.ensure_credit_budget_defaults()
        self.conn.commit()

    def ensure_alert_credit_columns(self) -> None:
        columns = {row["name"] for row in self.conn.execute("pragma table_info(alerts)").fetchall()}
        if "budget_credits" not in columns:
            self.conn.execute("alter table alerts add column budget_credits real not null default 0")
        if "current_credits" not in columns:
            self.conn.execute("alter table alerts add column current_credits real not null default 0")
        if "unit" not in columns:
            self.conn.execute("alter table alerts add column unit text not null default 'zar'")

    def ensure_account_limit_reset_time_column(self) -> None:
        columns = {row["name"] for row in self.conn.execute("pragma table_info(account_usage_limits)").fetchall()}
        if "reset_time" not in columns:
            self.conn.execute("alter table account_usage_limits add column reset_time text not null default '00:00'")

    def ensure_credit_budget_defaults(self) -> None:
        def as_float(key: str, default: float) -> float:
            try:
                return float(settings.get(key, default))
            except (TypeError, ValueError):
                return default

        rows = self.conn.execute("select key, value from settings").fetchall()
        settings = {row["key"]: row["value"] for row in rows}
        default_credits = {
            "daily_budget_credits": 100,
            "weekly_budget_credits": 700,
            "monthly_budget_credits": 3000,
        }
        for key, credit_value in default_credits.items():
            if str(settings.get(key, "")).strip():
                continue
            self.conn.execute(
                "insert into settings(key, value) values(?, ?) "
                "on conflict(key) do update set value=excluded.value",
                (key, str(credit_value)),
            )

    async def settings(self) -> dict[str, str]:
        def operation() -> dict[str, str]:
            rows = self.conn.execute("select key, value from settings").fetchall()
            return {row["key"]: row["value"] for row in rows}

        with timed_dependency("db.settings"):
            return await self._run_db(operation)

    async def update_settings(self, updates: dict[str, Any]) -> dict[str, str]:
        allowed = {
            "daily_budget_zar",
            "weekly_budget_zar",
            "monthly_budget_zar",
            "pricing_mode",
            "account_credit_limit_migration_done",
            "usd_zar_fallback_rate",
            "webhook_url",
            "dashboard_url",
            "dashboard_mode",
            "ui_theme",
            "unknown_account_mapping",
            *SESSION_SIGNAL_THRESHOLD_KEYS,
        }
        def operation() -> None:
            for key, value in updates.items():
                if key not in allowed:
                    continue
                if key == "webhook_url" and str(value).strip():
                    try:
                        validate_outbound_url(str(value).strip(), key)
                    except ValueError:
                        continue
                self.conn.execute(
                    "insert into settings(key, value) values(?, ?) "
                    "on conflict(key) do update set value=excluded.value",
                    (key, str(value)),
                )
            self.conn.commit()

        with timed_dependency("db.update_settings"):
            await self._run_db(operation)
        return await self.settings()

    async def cache_generation(self) -> int:
        return await self.setting_generation("cache_generation")

    async def setting_generation(self, key: str) -> int:
        def operation() -> int:
            row = self.conn.execute("select value from settings where key = ?", (key,)).fetchone()
            try:
                generation = int(str(row["value"] if row else "1"))
            except ValueError:
                generation = 1
            if row is None or generation < 1:
                self.conn.execute(
                    "insert into settings(key, value) values(?, '1') "
                    "on conflict(key) do update set value='1'",
                    (key,),
                )
                self.conn.commit()
                return 1
            return generation

        with timed_dependency("db.setting_generation", key=key):
            return await self._run_db(operation)

    async def bump_cache_generation(self, reason: str) -> int:
        return await self.bump_setting_generation("cache_generation", reason)

    async def bump_setting_generation(self, key: str, reason: str) -> int:
        def operation() -> int:
            self.conn.execute("insert or ignore into settings(key, value) values(?, '1')", (key,))
            self.conn.execute(
                "update settings set value = cast(value as integer) + 1 where key = ?",
                (key,),
            )
            row = self.conn.execute("select value from settings where key = ?", (key,)).fetchone()
            self.conn.commit()
            return int(row["value"])

        with timed_dependency("db.bump_setting_generation", key=key, reason=reason):
            return await self._run_db(operation)

    async def save_fx_rate(self, day: date, rate: float, source: str) -> None:
        def operation() -> None:
            self.conn.execute(
                "insert into fx_rates(day, usd_zar, source, fetched_at) values(?, ?, ?, ?) "
                "on conflict(day) do update set usd_zar=excluded.usd_zar, "
                "source=excluded.source, fetched_at=excluded.fetched_at",
                (day.isoformat(), rate, source, datetime.now(timezone.utc).isoformat()),
            )
            self.conn.commit()

        with timed_dependency("db.save_fx_rate", day=day.isoformat()):
            await self._run_db(operation)

    async def get_fx_rate(self, day: date) -> dict[str, Any] | None:
        def operation() -> dict[str, Any] | None:
            row = self.conn.execute("select * from fx_rates where day = ?", (day.isoformat(),)).fetchone()
            return dict(row) if row else None

        with timed_dependency("db.get_fx_rate", day=day.isoformat()):
            return await self._run_db(operation)

    async def latest_alert_ratio(self, period: str, start: date, end: date) -> float:
        def operation() -> float:
            row = self.conn.execute(
                "select max(threshold_ratio) as threshold_ratio from alerts "
                "where period = ? and period_start = ? and period_end = ?",
                (period, start.isoformat(), end.isoformat()),
            ).fetchone()
            return float(row["threshold_ratio"] or 0)

        with timed_dependency("db.latest_alert_ratio", period=period):
            return await self._run_db(operation)

    async def record_alert(self, payload: dict[str, Any], threshold_ratio: float) -> None:
        def operation() -> None:
            self.conn.execute(
                "insert into alerts(created_at, period, period_start, period_end, threshold_ratio, "
                "budget_zar, current_zar, budget_credits, current_credits, unit, payload) "
                "values(?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    datetime.now(timezone.utc).isoformat(),
                    payload["period"],
                    payload["period_start"],
                    payload["period_end"],
                    threshold_ratio,
                    payload.get("budget_zar", 0),
                    payload.get("current_zar", 0),
                    payload.get("budget_credits", 0),
                    payload.get("current_credits", 0),
                    payload.get("unit", "credits"),
                    json.dumps(payload, sort_keys=True),
                ),
            )
            self.conn.commit()

        with timed_dependency("db.record_alert", period=payload["period"]):
            await self._run_db(operation)

    async def alerts(self, limit: int = 50) -> list[dict[str, Any]]:
        def operation() -> list[dict[str, Any]]:
            budget_rows = self.conn.execute(
                "select * from alerts order by id desc limit ?", (limit,)
            ).fetchall()
            account_rows = self.conn.execute(
                "select * from account_limit_alerts order by id desc limit ?", (limit,)
            ).fetchall()
            burn_rows = self.conn.execute(
                "select * from account_burn_alerts order by id desc limit ?", (limit,)
            ).fetchall()
            result = []
            for row in budget_rows:
                item = dict(row)
                item["payload"] = json.loads(item["payload"])
                result.append(item)
            for row in account_rows:
                item = dict(row)
                item["payload"] = json.loads(item["payload"])
                item.update(item["payload"])
                result.append(item)
            for row in burn_rows:
                item = dict(row)
                item["payload"] = json.loads(item["payload"])
                item.update(item["payload"])
                result.append(item)
            return sorted(result, key=lambda item: item["created_at"], reverse=True)[:limit]

        with timed_dependency("db.alerts", limit=limit):
            return await self._run_db(operation)

    async def record_summary_once(self, summary_for: date, slot: str, payload: dict[str, Any]) -> bool:
        def operation() -> bool:
            cursor = self.conn.execute(
                "insert or ignore into summaries(created_at, summary_for, slot, payload) values(?, ?, ?, ?)",
                (
                    datetime.now(timezone.utc).isoformat(),
                    summary_for.isoformat(),
                    slot,
                    json.dumps(payload, sort_keys=True),
                ),
            )
            self.conn.commit()
            return bool(cursor.rowcount)

        with timed_dependency("db.record_summary_once", day=summary_for.isoformat(), slot=slot):
            return await self._run_db(operation)

    async def record_auth_snapshot(self, snapshot: dict[str, Any]) -> bool:
        observed_at = snapshot["observed_at"]
        account_id = snapshot.get("account_id") or None
        email = snapshot.get("email") or None
        name = snapshot.get("name") or None
        source = snapshot.get("source") or AUTH_SNAPSHOT_SOURCE
        def operation() -> bool:
            latest = self.conn.execute(
                "select account_id, email, name, source from auth_snapshots order by observed_at desc, id desc limit 1"
            ).fetchone()
            if latest and (
                latest["account_id"],
                latest["email"],
                latest["name"],
                latest["source"],
            ) == (account_id, email, name, source):
                return False
            self.conn.execute(
                "insert into auth_snapshots(observed_at, account_id, email, name, source) values(?, ?, ?, ?, ?)",
                (observed_at, account_id, email, name, source),
            )
            self.conn.commit()
            return True

        with timed_dependency("db.record_auth_snapshot"):
            return await self._run_db(operation)

    async def auth_snapshots(self, limit: int = 200) -> list[dict[str, Any]]:
        def operation() -> list[dict[str, Any]]:
            rows = self.conn.execute(
                "select * from auth_snapshots order by observed_at desc, id desc limit ?",
                (limit,),
            ).fetchall()
            return [dict(row) for row in rows]

        with timed_dependency("db.auth_snapshots", limit=limit):
            return await self._run_db(operation)

    async def usage_aggregate_days(self, cache_version: str, start: date, end: date) -> set[str]:
        def operation() -> set[str]:
            rows = self.conn.execute(
                "select day from usage_daily_aggregate_days "
                "where cache_version = ? and day >= ? and day <= ?",
                (cache_version, start.isoformat(), end.isoformat()),
            ).fetchall()
            return {str(row["day"]) for row in rows}

        with timed_dependency("db.usage_aggregate_days", start=start.isoformat(), end=end.isoformat()):
            return await self._run_db(operation)

    async def usage_aggregate_warnings(self, cache_version: str, start: date, end: date) -> list[str]:
        def operation() -> list[str]:
            warnings: set[str] = set()
            rows = self.conn.execute(
                "select warnings from usage_daily_aggregate_days "
                "where cache_version = ? and day >= ? and day <= ?",
                (cache_version, start.isoformat(), end.isoformat()),
            ).fetchall()
            for row in rows:
                try:
                    warnings.update(str(item) for item in json.loads(row["warnings"]))
                except json.JSONDecodeError:
                    continue
            return sorted(warnings)

        with timed_dependency("db.usage_aggregate_warnings", start=start.isoformat(), end=end.isoformat()):
            return await self._run_db(operation)

    async def usage_aggregate_rows(
        self,
        cache_version: str,
        start: date,
        end: date,
        account_filter: set[str] | None = None,
    ) -> list[dict[str, Any]]:
        params: list[Any] = [cache_version, start.isoformat(), end.isoformat()]
        account_clause = ""
        if account_filter:
            placeholders = ",".join("?" for _ in account_filter)
            account_clause = f" and account in ({placeholders})"
            params.extend(sorted(account_filter))
        def operation() -> list[dict[str, Any]]:
            rows = self.conn.execute(
                "select * from usage_daily_aggregates "
                "where cache_version = ? and day >= ? and day <= ?"
                f"{account_clause}",
                tuple(params),
            ).fetchall()
            return [dict(row) for row in rows]

        with timed_dependency("db.usage_aggregate_rows", start=start.isoformat(), end=end.isoformat()):
            return await self._run_db(operation)

    async def prune_usage_aggregate_cache_schemas(self, current_schema: str) -> dict[str, int]:
        keep_pattern = f"{current_schema}:%"
        def operation() -> dict[str, int]:
            aggregate_cursor = self.conn.execute(
                "delete from usage_daily_aggregates where cache_version not like ?",
                (keep_pattern,),
            )
            day_cursor = self.conn.execute(
                "delete from usage_daily_aggregate_days where cache_version not like ?",
                (keep_pattern,),
            )
            self.conn.commit()
            return {
                "aggregate_rows": max(int(aggregate_cursor.rowcount or 0), 0),
                "day_markers": max(int(day_cursor.rowcount or 0), 0),
            }

        with timed_dependency("db.prune_usage_aggregate_cache_schemas", current_schema=current_schema):
            deleted = await self._run_db(operation)
        if deleted["aggregate_rows"] or deleted["day_markers"]:
            logger.info(
                "usage_aggregate_cache_pruned current_schema=%s aggregate_rows=%s day_markers=%s",
                current_schema,
                deleted["aggregate_rows"],
                deleted["day_markers"],
            )
        return deleted

    async def save_usage_daily_aggregate(
        self,
        cache_version: str,
        day: date,
        rows: list[dict[str, Any]],
        warnings: list[str],
    ) -> None:
        def operation() -> None:
            self.conn.execute(
                "delete from usage_daily_aggregates where cache_version = ? and day = ?",
                (cache_version, day.isoformat()),
            )
            self.conn.executemany(
                "insert into usage_daily_aggregates("
                "cache_version, day, account, model, effort, input_tokens, cached_input_tokens, "
                "output_tokens, reasoning_output_tokens, total_tokens, input_usd, cached_input_usd, "
                "output_usd, reasoning_output_usd, total_usd, input_credits, cached_input_credits, "
                "output_credits, reasoning_output_credits, total_credits, long_context_applied, "
                "events, sessions, files) values(?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                [
                    (
                        cache_version,
                        row["day"],
                        row["account"],
                        row["model"],
                        row["effort"],
                        row["input_tokens"],
                        row["cached_input_tokens"],
                        row["output_tokens"],
                        row["reasoning_output_tokens"],
                        row["total_tokens"],
                        row["input_usd"],
                        row["cached_input_usd"],
                        row["output_usd"],
                        row["reasoning_output_usd"],
                        row["total_usd"],
                        row["input_credits"],
                        row["cached_input_credits"],
                        row["output_credits"],
                        row["reasoning_output_credits"],
                        row["total_credits"],
                        1 if row["long_context_applied"] else 0,
                        row["events"],
                        json.dumps(sorted(row["sessions"])),
                        json.dumps(sorted(row["files"])),
                    )
                    for row in rows
                ],
            )
            self.conn.execute(
                "insert into usage_daily_aggregate_days(cache_version, day, generated_at, warnings) values(?, ?, ?, ?) "
                "on conflict(cache_version, day) do update set generated_at=excluded.generated_at, warnings=excluded.warnings",
                (
                    cache_version,
                    day.isoformat(),
                    datetime.now(timezone.utc).isoformat(),
                    json.dumps(warnings, sort_keys=True),
                ),
            )
            self.conn.commit()

        with timed_dependency("db.save_usage_daily_aggregate", day=day.isoformat(), rows=len(rows)):
            await self._run_db(operation)

    async def account_limits(self, enabled_only: bool = False) -> list[dict[str, Any]]:
        query = "select * from account_usage_limits"
        params: tuple[Any, ...] = ()
        if enabled_only:
            query += " where enabled = 1"
        query += " order by account"
        def operation() -> list[dict[str, Any]]:
            rows = self.conn.execute(query, params).fetchall()
            return [dict(row) for row in rows]

        with timed_dependency("db.account_limits", enabled_only=enabled_only):
            return await self._run_db(operation)

    async def upsert_account_limit(self, payload: dict[str, Any]) -> dict[str, Any]:
        now = datetime.now(timezone.utc).isoformat()
        account = str(payload["account"]).strip().lower()
        metric = str(payload.get("metric") or "total_tokens")
        cap_value = float(payload["cap_value"])
        reset_weekday = int(payload.get("reset_weekday", 4))
        reset_time = str(payload.get("reset_time") or "00:00")
        tz_name = str(payload.get("timezone") or DEFAULT_TZ)
        thresholds = payload.get("thresholds", [0.7, 0.85, 0.95, 1.0])
        enabled = 1 if payload.get("enabled", True) else 0
        def operation() -> dict[str, Any]:
            self.conn.execute(
                "insert into account_usage_limits(account, metric, cap_value, reset_weekday, reset_time, timezone, "
                "thresholds, enabled, created_at, updated_at) values(?, ?, ?, ?, ?, ?, ?, ?, ?, ?) "
                "on conflict(account) do update set metric=excluded.metric, cap_value=excluded.cap_value, "
                "reset_weekday=excluded.reset_weekday, reset_time=excluded.reset_time, "
                "timezone=excluded.timezone, thresholds=excluded.thresholds, "
                "enabled=excluded.enabled, updated_at=excluded.updated_at",
                (
                    account,
                    metric,
                    cap_value,
                    reset_weekday,
                    reset_time,
                    tz_name,
                    json.dumps(thresholds),
                    enabled,
                    now,
                    now,
                ),
            )
            self.conn.commit()
            row = self.conn.execute("select * from account_usage_limits where account = ?", (account,)).fetchone()
            return dict(row)

        with timed_dependency("db.upsert_account_limit", account=account):
            row = await self._run_interactive_db(operation)
        return row

    async def ensure_account_limit(self, payload: dict[str, Any]) -> tuple[dict[str, Any], bool]:
        now = datetime.now(timezone.utc).isoformat()
        account = str(payload["account"]).strip().lower()
        metric = str(payload.get("metric") or "total_tokens")
        cap_value = float(payload["cap_value"])
        reset_weekday = int(payload.get("reset_weekday", 4))
        reset_time = str(payload.get("reset_time") or "00:00")
        tz_name = str(payload.get("timezone") or DEFAULT_TZ)
        thresholds = payload.get("thresholds", [0.7, 0.85, 0.95, 1.0])
        enabled = 1 if payload.get("enabled", True) else 0
        def operation() -> tuple[dict[str, Any], bool]:
            existing = self.conn.execute(
                "select id from account_usage_limits where account = ?",
                (account,),
            ).fetchone()
            self.conn.execute(
                "insert or ignore into account_usage_limits(account, metric, cap_value, reset_weekday, reset_time, timezone, "
                "thresholds, enabled, created_at, updated_at) values(?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    account,
                    metric,
                    cap_value,
                    reset_weekday,
                    reset_time,
                    tz_name,
                    json.dumps(thresholds),
                    enabled,
                    now,
                    now,
                ),
            )
            self.conn.commit()
            row = self.conn.execute("select * from account_usage_limits where account = ?", (account,)).fetchone()
            return dict(row), existing is None

        with timed_dependency("db.ensure_account_limit", account=account):
            return await self._run_db(operation)

    async def latest_account_limit_threshold(
        self,
        account: str,
        metric: str,
        window_start: str,
        window_end: str,
    ) -> float:
        def operation() -> float:
            row = self.conn.execute(
                "select max(threshold_ratio) as threshold_ratio from account_limit_alerts "
                "where account = ? and metric = ? and window_start = ? and window_end = ?",
                (account, metric, window_start, window_end),
            ).fetchone()
            return float(row["threshold_ratio"] or 0)

        with timed_dependency("db.latest_account_limit_threshold", account=account):
            return await self._run_db(operation)

    async def record_account_limit_alert(self, payload: dict[str, Any], threshold_ratio: float) -> bool:
        def operation() -> bool:
            cursor = self.conn.execute(
                "insert or ignore into account_limit_alerts(created_at, account, metric, window_start, window_end, "
                "threshold_ratio, payload) values(?, ?, ?, ?, ?, ?, ?)",
                (
                    datetime.now(timezone.utc).isoformat(),
                    payload["account"],
                    payload["metric"],
                    payload["window_start"],
                    payload["window_end"],
                    threshold_ratio,
                    json.dumps(payload, sort_keys=True),
                ),
            )
            self.conn.commit()
            return bool(cursor.rowcount)

        with timed_dependency("db.record_account_limit_alert", account=payload["account"]):
            return await self._run_db(operation)

    async def record_account_burn_alert(self, payload: dict[str, Any]) -> bool:
        def operation() -> bool:
            cursor = self.conn.execute(
                "insert or ignore into account_burn_alerts(created_at, account, advisory_id, severity, window_start, window_end, payload) "
                "values(?, ?, ?, ?, ?, ?, ?)",
                (
                    datetime.now(timezone.utc).isoformat(),
                    payload["account"],
                    payload["advisory_id"],
                    payload["severity"],
                    payload["window_start"],
                    payload["window_end"],
                    json.dumps(payload, sort_keys=True),
                ),
            )
            self.conn.commit()
            return bool(cursor.rowcount)

        with timed_dependency("db.record_account_burn_alert", account=payload["account"]):
            return await self._run_db(operation)
