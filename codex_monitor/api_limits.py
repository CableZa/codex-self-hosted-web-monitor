from __future__ import annotations

import json
import os
import math
from dataclasses import dataclass
from datetime import date, datetime, time, timedelta
from typing import Any
from zoneinfo import ZoneInfo

try:
    from fastapi import HTTPException
except ImportError:  # pragma: no cover
    class HTTPException(Exception):
        def __init__(self, status_code: int, detail: str):
            super().__init__(detail)
            self.status_code = status_code
            self.detail = detail

from .api_dates import now_local

DEFAULT_TZ = os.environ.get("TIMEZONE", "UTC")
SEVERITY_RANK = {"ok": 0, "info": 1, "warning": 2, "critical": 3}


@dataclass(frozen=True)
class BudgetStatus:
    period: str
    start: date
    end: date
    budget_zar: float
    current_zar: float
    budget_credits: float
    current_credits: float
    unit: str
    ratio: float
    exceeded: bool
    next_repeat_ratio: float


@dataclass(frozen=True)
class AccountBurnAdvisory:
    id: str
    severity: str
    message: str
    label: str
    value: str


@dataclass(frozen=True)
class AccountLimitStatus:
    id: int
    account: str
    metric: str
    cap_value: float
    current_value: float
    ratio: float
    remaining_value: float
    window_start: date
    window_end: date
    window_start_at: str
    window_end_at: str
    reset_at: str
    reset_weekday: int
    reset_time: str
    timezone: str
    thresholds: list[float]
    crossed_thresholds: list[float]
    next_threshold: float | None
    exceeded: bool
    enabled: bool
    elapsed_days: int
    remaining_days: int
    safe_daily_spend: float
    spend_rate_vs_target: float
    projected_exhaustion_date: str | None
    projected_exhaustion_label: str
    burn_severity: str
    burn_advisories: list[AccountBurnAdvisory]


def parse_thresholds(value: Any) -> list[float]:
    if isinstance(value, str):
        try:
            value = json.loads(value)
        except json.JSONDecodeError:
            value = []
    if not isinstance(value, list):
        value = []
    thresholds = []
    for item in value:
        try:
            number = float(item)
        except (TypeError, ValueError):
            continue
        if 0 < number <= 1:
            thresholds.append(number)
    return sorted(set(thresholds)) or [0.7, 0.85, 0.95, 1.0]


def validate_account_limit_payload(payload: dict[str, Any]) -> dict[str, Any]:
    account = str(payload.get("account") or "").strip().lower()
    if not account:
        raise HTTPException(status_code=400, detail="account is required")
    metric = str(payload.get("metric") or "total_tokens")
    if metric not in {"total_tokens", "total_credits"}:
        raise HTTPException(status_code=400, detail="only total_tokens and total_credits are supported")
    try:
        cap_value = float(payload.get("cap_value"))
    except (TypeError, ValueError):
        raise HTTPException(status_code=400, detail="cap_value must be a number") from None
    if cap_value <= 0:
        raise HTTPException(status_code=400, detail="cap_value must be positive")
    if not cap_value.is_integer():
        raise HTTPException(status_code=400, detail="cap_value must be a whole number")
    reset_weekday = int(payload.get("reset_weekday", 4))
    if reset_weekday < 0 or reset_weekday > 6:
        raise HTTPException(status_code=400, detail="reset_weekday must be 0 to 6")
    reset_time = str(payload.get("reset_time") or "00:00")
    try:
        parsed_reset_time = time.fromisoformat(reset_time)
    except ValueError:
        raise HTTPException(status_code=400, detail="reset_time must be HH:MM") from None
    if parsed_reset_time.second or parsed_reset_time.microsecond:
        raise HTTPException(status_code=400, detail="reset_time must be HH:MM")
    reset_time = f"{parsed_reset_time.hour:02d}:{parsed_reset_time.minute:02d}"
    timezone_name = str(payload.get("timezone") or DEFAULT_TZ)
    try:
        ZoneInfo(timezone_name)
    except Exception:
        raise HTTPException(status_code=400, detail="timezone is invalid") from None
    return {
        "account": account,
        "metric": metric,
        "cap_value": cap_value,
        "reset_weekday": reset_weekday,
        "reset_time": reset_time,
        "timezone": timezone_name,
        "thresholds": parse_thresholds(payload.get("thresholds", [0.7, 0.85, 0.95, 1.0])),
        "enabled": bool(payload.get("enabled", True)),
    }


def reset_window_for_day(day: date, reset_weekday: int) -> tuple[date, date]:
    days_since_reset = (day.weekday() - reset_weekday) % 7
    start = day - timedelta(days=days_since_reset)
    end = start + timedelta(days=6)
    return start, end


def reset_at_iso(window_end: date, tz_name: str) -> str:
    tz = ZoneInfo(tz_name)
    reset_day = window_end + timedelta(days=1)
    return datetime.combine(reset_day, time.min, tzinfo=tz).isoformat()


def parse_reset_time(value: Any) -> time:
    try:
        parsed = time.fromisoformat(str(value or "00:00"))
    except ValueError:
        return time.min
    return parsed.replace(second=0, microsecond=0)


def reset_window_for_datetime(now: datetime, reset_weekday: int, reset_time: str) -> tuple[datetime, datetime]:
    reset_clock = parse_reset_time(reset_time)
    local_now = now if now.tzinfo else now.replace(tzinfo=ZoneInfo(DEFAULT_TZ))
    days_since_reset = (local_now.weekday() - reset_weekday) % 7
    start_day = local_now.date() - timedelta(days=days_since_reset)
    start = datetime.combine(start_day, reset_clock, tzinfo=local_now.tzinfo)
    if local_now < start:
        start -= timedelta(days=7)
    return start, start + timedelta(days=7)


def resolve_window_reference_time(target: date | datetime | None, tz_name: str) -> datetime:
    current = now_local(tz_name)
    if target is None:
        return current
    if isinstance(target, datetime):
        if target.tzinfo is None:
            return target.replace(tzinfo=ZoneInfo(tz_name))
        return target.astimezone(ZoneInfo(tz_name))
    if target == current.date():
        return current
    return datetime.combine(target, time.max, tzinfo=ZoneInfo(tz_name))


def format_limit_value(value: float, metric: str) -> str:
    rounded = round(float(value), 2)
    if metric == "total_credits":
        if rounded.is_integer():
            return f"{int(rounded)} credits"
        return f"{rounded:.2f}".rstrip("0").rstrip(".") + " credits"
    return f"{int(round(rounded))} tokens"


def max_severity(severities: list[str]) -> str:
    return max(severities, key=lambda severity: SEVERITY_RANK.get(severity, 0), default="ok")


def advisory_dict(advisory: AccountBurnAdvisory) -> dict[str, Any]:
    return {
        "id": advisory.id,
        "severity": advisory.severity,
        "message": advisory.message,
        "label": advisory.label,
        "value": advisory.value,
    }


def advisory_from_dict(value: dict[str, Any]) -> AccountBurnAdvisory:
    return AccountBurnAdvisory(
        id=str(value.get("id") or ""),
        severity=str(value.get("severity") or "info"),
        message=str(value.get("message") or ""),
        label=str(value.get("label") or ""),
        value=str(value.get("value") or ""),
    )


def projected_exhaustion(
    current_value: float,
    cap_value: float,
    elapsed_days: int,
    window_end: date,
    today: date,
    tz_name: str,
) -> tuple[str | None, str]:
    if cap_value <= 0:
        return None, "Not projected this window"
    average_daily_spend = current_value / elapsed_days if elapsed_days > 0 else 0
    if current_value >= cap_value:
        return today.isoformat(), "Already exhausted"
    if average_daily_spend <= 0:
        return None, "Not projected this window"
    days_until_exhaustion = math.ceil((cap_value - current_value) / average_daily_spend)
    projected = today + timedelta(days=max(days_until_exhaustion, 0))
    if projected > window_end:
        return None, "Not projected this window"
    return projected.isoformat(), datetime.combine(projected, time(12), tzinfo=ZoneInfo(tz_name)).strftime("%A")


def burn_advisories_for_status(
    metric: str,
    cap_value: float,
    current_value: float,
    remaining_value: float,
    remaining_days: int,
    spend_rate_vs_target: float,
    safe_daily_spend: float,
    projected_exhaustion_date: str | None,
    projected_exhaustion_label: str,
    today: date,
    window_days: int,
) -> list[AccountBurnAdvisory]:
    advisories: list[AccountBurnAdvisory] = []
    daily_target = cap_value / window_days if window_days > 0 else 0

    if current_value >= cap_value:
        advisories.append(
            AccountBurnAdvisory(
                id="window-exhausted",
                severity="critical",
                message="Weekly account limit is already exhausted.",
                label="Remaining",
                value=format_limit_value(0, metric),
            )
        )
    elif projected_exhaustion_date:
        advisories.append(
            AccountBurnAdvisory(
                id="projected-exhaustion",
                severity="critical" if projected_exhaustion_date <= today.isoformat() else "warning",
                message=f"At current pace you will run out by {projected_exhaustion_label}.",
                label="Projected",
                value=projected_exhaustion_label,
            )
        )

    if remaining_days >= 2 and remaining_value > 0 and daily_target > 0 and safe_daily_spend < daily_target * 0.75:
        advisories.append(
            AccountBurnAdvisory(
                id="thin-runway",
                severity="critical" if safe_daily_spend < daily_target * 0.4 else "warning",
                message=f"{format_limit_value(remaining_value, metric)} left across {remaining_days} days.",
                label="Safe daily pace",
                value=f"{format_limit_value(safe_daily_spend, metric)}/day",
            )
        )

    return advisories[:3]


def account_limit_status_from_dict(value: dict[str, Any]) -> AccountLimitStatus:
    return AccountLimitStatus(
        id=int(value["id"]),
        account=str(value["account"]),
        metric=str(value["metric"]),
        cap_value=float(value["cap_value"]),
        current_value=float(value["current_value"]),
        ratio=float(value["ratio"]),
        remaining_value=float(value["remaining_value"]),
        window_start=date.fromisoformat(str(value["window_start"])),
        window_end=date.fromisoformat(str(value["window_end"])),
        window_start_at=str(value["window_start_at"]),
        window_end_at=str(value["window_end_at"]),
        reset_at=str(value["reset_at"]),
        reset_weekday=int(value["reset_weekday"]),
        reset_time=str(value.get("reset_time") or "00:00"),
        timezone=str(value["timezone"]),
        thresholds=[float(item) for item in value["thresholds"]],
        crossed_thresholds=[float(item) for item in value["crossed_thresholds"]],
        next_threshold=float(value["next_threshold"]) if value.get("next_threshold") is not None else None,
        exceeded=bool(value["exceeded"]),
        enabled=bool(value["enabled"]),
        elapsed_days=int(value.get("elapsed_days") or 0),
        remaining_days=int(value.get("remaining_days") or 0),
        safe_daily_spend=float(value.get("safe_daily_spend") or 0),
        spend_rate_vs_target=float(value.get("spend_rate_vs_target") or 0),
        projected_exhaustion_date=str(value["projected_exhaustion_date"]) if value.get("projected_exhaustion_date") else None,
        projected_exhaustion_label=str(value.get("projected_exhaustion_label") or "Not projected this window"),
        burn_severity=str(value.get("burn_severity") or "ok"),
        burn_advisories=[
            advisory_from_dict(item)
            for item in value.get("burn_advisories", [])
            if isinstance(item, dict)
        ],
    )


def account_limit_status_from_report(
    limit: dict[str, Any],
    report: dict[str, Any],
    today: date | datetime | None = None,
    window_start_at: datetime | None = None,
    window_end_at: datetime | None = None,
) -> AccountLimitStatus:
    tz_name = str(limit.get("timezone") or DEFAULT_TZ)
    reset_weekday = int(limit.get("reset_weekday", 4))
    reset_time = str(limit.get("reset_time") or "00:00")
    local_now = resolve_window_reference_time(today, tz_name)
    if window_start_at is None or window_end_at is None:
        window_start_at, window_end_at = reset_window_for_datetime(local_now, reset_weekday, reset_time)
    window_start = window_start_at.date()
    window_end = (window_end_at - timedelta(microseconds=1)).date()
    thresholds = parse_thresholds(limit.get("thresholds"))
    metric = str(limit.get("metric") or "total_tokens")
    current_value = float(report.get("totals", {}).get(metric, 0))
    cap_value = float(limit["cap_value"])
    remaining_value = max(cap_value - current_value, 0)
    ratio = current_value / cap_value if cap_value > 0 else 0
    crossed = [threshold for threshold in thresholds if ratio >= threshold]
    next_threshold = next((threshold for threshold in thresholds if ratio < threshold), None)
    today_local = local_now.date()
    window_days = max((window_end_at.date() - window_start_at.date()).days, 1)
    elapsed_days = min(max((today_local - window_start_at.date()).days + 1, 1), window_days)
    remaining_days = max((window_end - today_local).days + 1, 0)
    safe_daily_spend = remaining_value / remaining_days if remaining_days > 0 else 0
    target_to_date = cap_value * (elapsed_days / window_days) if window_days > 0 else 0
    spend_rate_vs_target = current_value / target_to_date if target_to_date > 0 else 0
    projected_exhaustion_date, projected_exhaustion_label = projected_exhaustion(
        current_value,
        cap_value,
        elapsed_days,
        window_end,
        today_local,
        tz_name,
    )
    burn_advisories = burn_advisories_for_status(
        metric,
        cap_value,
        current_value,
        remaining_value,
        remaining_days,
        spend_rate_vs_target,
        safe_daily_spend,
        projected_exhaustion_date,
        projected_exhaustion_label,
        today_local,
        window_days,
    )
    return AccountLimitStatus(
        id=int(limit["id"]),
        account=str(limit["account"]),
        metric=metric,
        cap_value=cap_value,
        current_value=current_value,
        ratio=ratio,
        remaining_value=remaining_value,
        window_start=window_start,
        window_end=window_end,
        window_start_at=window_start_at.isoformat(),
        window_end_at=window_end_at.isoformat(),
        reset_at=window_end_at.isoformat(),
        reset_weekday=reset_weekday,
        reset_time=reset_time,
        timezone=tz_name,
        thresholds=thresholds,
        crossed_thresholds=crossed,
        next_threshold=next_threshold,
        exceeded=ratio >= 1,
        enabled=bool(limit.get("enabled", 1)),
        elapsed_days=elapsed_days,
        remaining_days=remaining_days,
        safe_daily_spend=safe_daily_spend,
        spend_rate_vs_target=spend_rate_vs_target,
        projected_exhaustion_date=projected_exhaustion_date,
        projected_exhaustion_label=projected_exhaustion_label,
        burn_severity=max_severity([advisory.severity for advisory in burn_advisories]),
        burn_advisories=burn_advisories,
    )


def account_limit_status_dict(status: AccountLimitStatus) -> dict[str, Any]:
    return {
        **status.__dict__,
        "window_start": status.window_start.isoformat(),
        "window_end": status.window_end.isoformat(),
        "window_start_at": status.window_start_at,
        "window_end_at": status.window_end_at,
        "burn_advisories": [advisory_dict(advisory) for advisory in status.burn_advisories],
    }
