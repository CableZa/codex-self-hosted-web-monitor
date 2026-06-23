from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator


class FlexibleModel(BaseModel):
    model_config = ConfigDict(extra="allow")


class CacheMeta(BaseModel):
    hit: bool
    ttl_seconds: int
    served_at: str


class Period(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    from_: str = Field(alias="from")
    to: str


class ExchangeRate(BaseModel):
    rate: float
    source: str
    day: str


class UsageTotals(FlexibleModel):
    input_tokens: int = 0
    cached_input_tokens: int = 0
    uncached_input_tokens: int = 0
    output_tokens: int = 0
    reasoning_output_tokens: int = 0
    total_tokens: int = 0
    input_usd: float = 0
    cached_input_usd: float = 0
    output_usd: float = 0
    reasoning_output_usd: float = 0
    total_usd: float = 0
    total_zar: float = 0
    input_credits: float = 0
    cached_input_credits: float = 0
    output_credits: float = 0
    reasoning_output_credits: float = 0
    total_credits: float = 0
    long_context_applied: bool = False
    long_context_events: int = 0
    max_input_tokens: int = 0
    cache_hit_ratio: float = 0
    events: int = 0
    sessions: int = 0
    files: int = 0


class UsageDay(UsageTotals):
    day: str


class BreakdownRow(UsageTotals):
    day: str | None = None
    model: str | None = None
    effort: str | None = None
    account: str | None = None


class SessionModelRow(UsageTotals):
    model: str


class SessionProjectRow(UsageTotals):
    project: str
    project_path: str | None = None


class AccountSwitchEvent(FlexibleModel):
    observed_at: str
    from_account: str | None = None
    to_account: str
    source: str | None = None


class SessionCacheReport(FlexibleModel):
    cache_efficiency: float = 0
    cached_input_tokens: int = 0
    uncached_input_tokens: int = 0
    inefficient_sessions: int = 0


class SessionWasteFinding(FlexibleModel):
    id: str
    severity: Literal["info", "warning", "critical"]
    label: str
    recommendation: str
    confidence: Literal["low", "medium", "high"]
    evidence: str
    estimated_waste_credits: float = 0
    estimated_waste_usd: float = 0


class UsageDiagnosticsReport(FlexibleModel):
    generated_at: str
    period: Period
    source_roots: list[str] = Field(default_factory=list)
    scan: dict[str, Any] = Field(default_factory=dict)
    parser: dict[str, Any] = Field(default_factory=dict)
    pricing: dict[str, Any] = Field(default_factory=dict)
    attribution: dict[str, Any] = Field(default_factory=dict)
    activity: dict[str, Any] = Field(default_factory=dict)
    confidence_grade: Literal["high", "medium", "low"]
    confidence_reasons: list[str] = Field(default_factory=list)
    cache: CacheMeta | None = None
    warnings: list[str] = Field(default_factory=list)


class SessionTimelineEvent(UsageTotals):
    timestamp: str
    day: str
    model: str
    effort: str
    account: str
    path: str
    priced_model: str | None = None


class PricingMetadata(FlexibleModel):
    currency: str | None = None
    unit: str | None = None
    updated: str | None = None
    credit_unit: str | None = None
    credit_source: str | None = None
    notes: list[Any] = Field(default_factory=list)


class SessionSummary(UsageTotals):
    session_id: str
    first_seen: str
    last_seen: str
    duration_seconds: int
    display_title: str | None = None
    first_message: str | None = None
    last_message: str | None = None
    summary: str | None = None
    project_name: str | None = None
    project_path: str | None = None
    cache_efficiency: float = 0
    long_context: bool = False
    long_context_reasons: list[str] = Field(default_factory=list)
    accounts: list[str] = Field(default_factory=list)
    efforts: list[str] = Field(default_factory=list)
    user_message_count: int = 0
    first_message_word_count: int = 0
    tool_call_count: int = 0
    tool_error_count: int = 0
    max_consecutive_tool_errors: int = 0
    repeated_tool_signatures: int = 0
    web_tool_call_count: int = 0
    large_ingest_count: int = 0
    waste_findings: list[SessionWasteFinding] = Field(default_factory=list)
    estimated_waste_credits: float = 0
    estimated_waste_usd: float = 0
    efficiency_score: int = 100
    efficiency_grade: Literal["S", "A", "B", "C", "D", "F"] = "S"
    by_model: list[SessionModelRow] = Field(default_factory=list)


class SessionDetail(SessionSummary):
    generated_at: str | None = None
    period: Period | None = None
    source_roots: list[str] = Field(default_factory=list)
    files_scanned: int = 0
    usage_events: int = 0
    pricing_metadata: PricingMetadata | None = None
    currency: dict[str, Any] | None = None
    exchange_rate: ExchangeRate | None = None
    cache: CacheMeta | None = None
    timeline: list[SessionTimelineEvent] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)


class SessionHistoryReport(FlexibleModel):
    generated_at: str | None = None
    period: Period
    source_roots: list[str] = Field(default_factory=list)
    files_scanned: int = 0
    usage_events: int = 0
    totals: UsageTotals
    sessions: list[SessionSummary] = Field(default_factory=list)
    top_sessions: list[SessionSummary] = Field(default_factory=list)
    by_project: list[SessionProjectRow] = Field(default_factory=list)
    account_switches: list[AccountSwitchEvent] = Field(default_factory=list)
    cache_report: SessionCacheReport | None = None
    warnings: list[str] = Field(default_factory=list)
    pricing_metadata: PricingMetadata | None = None
    currency: dict[str, Any] | None = None
    exchange_rate: ExchangeRate | None = None
    accounts: list[str] = Field(default_factory=list)
    cache: CacheMeta | None = None


class UsageReport(FlexibleModel):
    generated_at: str | None = None
    period: Period
    source_roots: list[str] = Field(default_factory=list)
    files_scanned: int = 0
    usage_events: int = 0
    totals: UsageTotals
    by_day: list[UsageDay] = Field(default_factory=list)
    by_week: list[UsageDay] = Field(default_factory=list)
    by_month: list[UsageDay] = Field(default_factory=list)
    by_model: list[BreakdownRow] = Field(default_factory=list)
    by_effort: list[BreakdownRow] = Field(default_factory=list)
    by_account: list[BreakdownRow] = Field(default_factory=list)
    by_day_model: list[BreakdownRow] = Field(default_factory=list)
    by_day_account: list[BreakdownRow] = Field(default_factory=list)
    by_model_effort: list[BreakdownRow] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    pricing_metadata: PricingMetadata | None = None
    currency: dict[str, Any] | None = None
    exchange_rate: ExchangeRate | None = None
    accounts: list[str] = Field(default_factory=list)
    cache: CacheMeta | None = None


class DaysReport(BaseModel):
    period: Period
    days: list[UsageDay]
    weeks: list[UsageDay] = Field(default_factory=list)
    months: list[UsageDay] = Field(default_factory=list)
    exchange_rate: ExchangeRate
    cache: CacheMeta | None = None


class AccountOption(FlexibleModel):
    account: str
    account_id: str | None = None
    email: str | None = None
    name: str | None = None
    source: str | None = None
    first_seen: str | None = None
    last_seen: str | None = None


class AuthSnapshot(FlexibleModel):
    id: int | None = None
    observed_at: str
    account_id: str | None = None
    email: str | None = None
    name: str | None = None
    source: str | None = None


class AttributionIssue(FlexibleModel):
    type: str
    severity: Literal["info", "warning", "critical"]
    recommended_action: str
    detail: str | None = None
    earliest_usage_day: str | None = None
    first_auth_snapshot_at: str | None = None
    unknown_usage_totals: UsageTotals | None = None


class AttributionHistory(FlexibleModel):
    earliest_usage_day: str | None = None
    latest_usage_day: str | None = None
    first_auth_snapshot_at: str | None = None
    visible_rollout_files: int = 0
    sessions_root_files: int = 0
    archived_sessions_root_files: int = 0
    unknown_usage_totals: UsageTotals | None = None


class AttributionReport(FlexibleModel):
    history: AttributionHistory
    issues: list[AttributionIssue] = Field(default_factory=list)


class AutoAccountLimitDefaults(FlexibleModel):
    email_suffixes: list[str] = Field(default_factory=list)
    cap_credits: float = 400
    reset_weekday: int = 4
    reset_time: str = "00:00"
    timezone: str = "UTC"
    thresholds: list[float] = Field(default_factory=lambda: [0.7, 0.85, 0.95, 1.0])


class AccountsReport(BaseModel):
    accounts: list[AccountOption]
    snapshots: list[AuthSnapshot]
    attribution: AttributionReport | None = None
    auto_account_limit_defaults: AutoAccountLimitDefaults = Field(default_factory=AutoAccountLimitDefaults)


class AuthSnapshotCreate(BaseModel):
    observed_at: str | None = None
    account_id: str | None = None
    email: str | None = None
    name: str | None = None
    source: str | None = None


class AuthSnapshotResult(BaseModel):
    inserted: bool
    snapshot: AuthSnapshotCreate


class Budget(FlexibleModel):
    period: Literal["today", "week", "month"]
    start: str
    end: str
    budget_zar: float
    current_zar: float
    budget_credits: float
    current_credits: float
    unit: Literal["credits", "zar"]
    ratio: float
    exceeded: bool
    next_repeat_ratio: float | None = None


class AccountLimit(FlexibleModel):
    id: int | None = None
    account: str
    metric: Literal["total_tokens", "total_credits"] = "total_tokens"
    cap_value: float
    reset_weekday: int = 4
    reset_time: str = "00:00"
    timezone: str
    thresholds: str | list[float]
    enabled: int | bool
    created_at: str | None = None
    updated_at: str | None = None


class AccountLimitUpdate(BaseModel):
    account: str
    metric: Literal["total_tokens", "total_credits"] = "total_tokens"
    cap_value: float
    reset_weekday: int = 4
    reset_time: str = "00:00"
    timezone: str | None = None
    thresholds: list[float] | str = Field(default_factory=lambda: [0.7, 0.85, 0.95, 1.0])
    enabled: bool = True

    @field_validator("account")
    @classmethod
    def account_required(cls, value: str) -> str:
        value = value.strip().lower()
        if not value:
            raise ValueError("account is required")
        return value


class AccountBurnAdvisory(FlexibleModel):
    id: str
    severity: Literal["info", "warning", "critical"]
    message: str
    label: str
    value: str


class AccountLimitStatus(FlexibleModel):
    id: int
    account: str
    metric: str
    cap_value: float
    current_value: float
    ratio: float
    remaining_value: float
    window_start: str
    window_end: str
    window_start_at: str
    window_end_at: str
    reset_at: str
    reset_weekday: int
    reset_time: str
    timezone: str
    thresholds: list[float]
    crossed_thresholds: list[float]
    next_threshold: float | None = None
    exceeded: bool
    enabled: bool
    elapsed_days: int = 0
    remaining_days: int = 0
    safe_daily_spend: float = 0
    spend_rate_vs_target: float = 0
    projected_exhaustion_date: str | None = None
    projected_exhaustion_label: str = "Not projected this window"
    burn_severity: Literal["ok", "info", "warning", "critical"] = "ok"
    burn_advisories: list[AccountBurnAdvisory] = Field(default_factory=list)


class AccountLimitsReport(BaseModel):
    limits: list[AccountLimit]
    statuses: list[AccountLimitStatus]
    status_state: str = "ready"


class AccountLimitPutResult(BaseModel):
    limit: AccountLimit
    status: AccountLimitStatus | None = None
    status_state: str = "ready"


class SnapshotResponse(FlexibleModel):
    version: str | None = None
    generated_at: str | None = None
    timezone: str | None = None
    reports: dict[str, UsageReport] | None = None
    budgets: list[Budget] | None = None
    account_limits: list[AccountLimitStatus] | None = None
    alerts_emitted: list[dict[str, Any]] | None = None
    cache: dict[str, Any] | None = None


class HealthResponse(BaseModel):
    ok: bool
    version: str
    generated_at: str | None = None
    error: str | None = None


class ChangelogGroup(BaseModel):
    name: str
    items: list[str] = Field(default_factory=list)


class ChangelogRelease(BaseModel):
    version: str | None = None
    date: str | None = None
    title: str
    groups: list[ChangelogGroup] = Field(default_factory=list)


class ChangelogReport(BaseModel):
    generated_at: str
    source: str
    releases: list[ChangelogRelease] = Field(default_factory=list)
    unreleased: ChangelogRelease | None = None


class UpdateStatusResponse(FlexibleModel):
    state: str
    generated_at: str
    checked_at: str | None = None
    current_version: str | None = None
    running_version: str | None = None
    latest_version: str | None = None
    latest_tag: str | None = None
    install_mode: str | None = None
    remote: str | None = None
    message: str | None = None
    error: str | None = None
    stale: bool = False


class SettingsUpdate(BaseModel):
    model_config = ConfigDict(extra="allow")

    daily_budget_zar: str | float | int | None = None
    weekly_budget_zar: str | float | int | None = None
    monthly_budget_zar: str | float | int | None = None
    pricing_mode: str | None = None
    usd_zar_fallback_rate: str | float | int | None = None
    webhook_url: str | None = None
    dashboard_url: str | None = None
    dashboard_mode: str | None = None
    ui_theme: str | None = None
    unknown_account_mapping: str | None = None
    session_high_input_tokens: str | float | int | None = None
    session_high_uncached_input_tokens: str | float | int | None = None
    session_low_cache_min_uncached_tokens: str | float | int | None = None
    session_low_cache_max_reuse_ratio: str | float | int | None = None
    session_large_total_tokens: str | float | int | None = None
    session_high_output_tokens: str | float | int | None = None
    session_long_context_pricing_signal_enabled: str | bool | None = None


class AlertResponse(FlexibleModel):
    id: int | None = None
    created_at: str | None = None
    type: str | None = None
    period: str | None = None
    payload: dict[str, Any] | None = None


class WebhookResult(FlexibleModel):
    sent: bool
    status: int | None = None
    reason: str | None = None


class RateCardRow(BaseModel):
    model: str
    input_credits: float | None = None
    cached_input_credits: float | None = None
    output_credits: float | None = None
    source: str | None = None


class RateCard(BaseModel):
    unit: str
    source: str | None = None
    updated: str | None = None
    fast_mode_detectable: bool
    fast_mode_note: str
    rows: list[RateCardRow]
