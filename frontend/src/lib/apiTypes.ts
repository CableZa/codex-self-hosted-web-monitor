export type CacheMeta = {
  hit: boolean;
  ttl_seconds: number;
  served_at: string;
};

export type CacheBackendStatus = {
  backend?: string;
  ok?: boolean;
  key_prefix?: string;
  aof_enabled?: boolean;
  rdb_changes_since_last_save?: number;
  fallback_reason?: string;
  memory_fallback_mode?: string;
  worker_count?: number;
  remote_dirty?: boolean;
  reason?: string;
};

export type SnapshotCacheStatus = {
  backend?: string | CacheBackendStatus;
  ok?: boolean;
  response?: CacheMeta;
};

export type UsageTotals = {
  input_tokens: number;
  cached_input_tokens?: number;
  uncached_input_tokens?: number;
  output_tokens: number;
  reasoning_output_tokens?: number;
  total_tokens: number;
  input_usd?: number;
  cached_input_usd?: number;
  output_usd?: number;
  reasoning_output_usd?: number;
  total_usd: number;
  total_zar: number;
  input_credits: number;
  cached_input_credits?: number;
  output_credits: number;
  reasoning_output_credits?: number;
  total_credits: number;
  long_context_applied?: boolean;
  long_context_events?: number;
  max_input_tokens?: number;
  cache_hit_ratio?: number;
  events?: number;
  sessions?: number;
  files?: number;
};

export type UsageDay = UsageTotals & {
  day: string;
  label?: string;
  start_day?: string;
  end_day?: string;
  week?: string;
  month?: string;
};

export type BreakdownRow = UsageTotals & {
  day?: string;
  model?: string;
  effort?: string;
  account?: string;
};

export type SessionModelRow = UsageTotals & {
  model: string;
};

export type SessionProjectRow = UsageTotals & {
  project: string;
  project_path?: string | null;
};

export type AccountSwitchEvent = {
  observed_at: string;
  from_account?: string | null;
  to_account: string;
  source?: string | null;
};

export type SessionCacheReport = {
  cache_efficiency: number;
  cached_input_tokens: number;
  uncached_input_tokens: number;
  inefficient_sessions: number;
};

export type SessionWasteFinding = {
  id: string;
  severity: "info" | "warning" | "critical";
  label: string;
  recommendation: string;
  confidence: "low" | "medium" | "high";
  evidence: string;
  estimated_waste_credits: number;
  estimated_waste_usd: number;
};

export type UsageDiagnosticsReport = {
  generated_at: string;
  period: { from: string; to: string };
  source_roots: string[];
  scan: Record<string, number | string>;
  parser: Record<string, number | string>;
  pricing: {
    unpriced_models?: string[];
    model_aliases?: string[];
    long_context_events?: number;
    pricing_updated?: string;
  };
  attribution: {
    unknown_account_events?: number;
    account_filter?: string[];
  };
  activity: Record<string, number | string>;
  confidence_grade: "high" | "medium" | "low";
  confidence_reasons: string[];
  cache?: CacheMeta;
  warnings: string[];
};

export type SessionTimelineEvent = UsageTotals & {
  timestamp: string;
  day: string;
  model: string;
  effort: string;
  account: string;
  path: string;
  priced_model?: string | null;
};

export type SessionSummary = UsageTotals & {
  session_id: string;
  first_seen: string;
  last_seen: string;
  duration_seconds: number;
  display_title?: string | null;
  first_message?: string | null;
  last_message?: string | null;
  summary?: string | null;
  project_name?: string | null;
  project_path?: string | null;
  cache_efficiency?: number;
  long_context?: boolean;
  long_context_reasons?: string[];
  accounts: string[];
  efforts?: string[];
  user_message_count?: number;
  first_message_word_count?: number;
  tool_call_count?: number;
  tool_error_count?: number;
  max_consecutive_tool_errors?: number;
  repeated_tool_signatures?: number;
  web_tool_call_count?: number;
  large_ingest_count?: number;
  waste_findings?: SessionWasteFinding[];
  estimated_waste_credits?: number;
  estimated_waste_usd?: number;
  efficiency_score?: number;
  efficiency_grade?: "S" | "A" | "B" | "C" | "D" | "F";
  by_model: SessionModelRow[];
};

export type SessionDetail = SessionSummary & {
  generated_at?: string;
  period?: { from: string; to: string };
  source_roots?: string[];
  files_scanned?: number;
  usage_events?: number;
  pricing_metadata?: PricingMetadata;
  currency?: { code?: string; usd_zar?: number };
  exchange_rate?: { rate: number; source: string; day: string };
  cache?: CacheMeta;
  timeline: SessionTimelineEvent[];
  warnings?: string[];
};

export type PricingMetadata = {
  currency?: string;
  unit?: string;
  updated?: string;
  credit_unit?: string;
  credit_source?: string;
  notes?: unknown[];
};

export type UsageReport = {
  generated_at?: string;
  period: { from: string; to: string };
  source_roots?: string[];
  files_scanned?: number;
  usage_events?: number;
  totals: UsageTotals;
  by_day: UsageDay[];
  by_week?: UsageDay[];
  by_month?: UsageDay[];
  by_model: BreakdownRow[];
  by_effort: BreakdownRow[];
  by_account: BreakdownRow[];
  by_day_model: BreakdownRow[];
  by_day_account: BreakdownRow[];
  by_model_effort: BreakdownRow[];
  exchange_rate: { rate: number; source: string; day: string };
  currency?: { code: string; usd_zar: number };
  accounts?: string[];
  cache?: CacheMeta;
  warnings?: string[];
  pricing_metadata?: PricingMetadata;
};

export type AccountOption = {
  account: string;
  account_id?: string;
  email?: string;
  name?: string;
  source?: string;
  first_seen?: string;
  last_seen?: string;
};

export type AuthSnapshot = {
  id?: number;
  observed_at: string;
  account_id?: string;
  email?: string;
  name?: string;
  source?: string;
};

export type AttributionIssue = {
  type: string;
  severity: "info" | "warning" | "critical";
  recommended_action: string;
  detail?: string | null;
  earliest_usage_day?: string | null;
  first_auth_snapshot_at?: string | null;
  unknown_usage_totals?: UsageTotals | null;
};

export type AttributionHistory = {
  earliest_usage_day?: string | null;
  latest_usage_day?: string | null;
  first_auth_snapshot_at?: string | null;
  visible_rollout_files: number;
  sessions_root_files: number;
  archived_sessions_root_files: number;
  unknown_usage_totals?: UsageTotals | null;
};

export type AttributionReport = {
  history: AttributionHistory;
  issues: AttributionIssue[];
};

export type AutoAccountLimitDefaults = {
  email_suffixes: string[];
  cap_credits: number;
  reset_weekday: number;
  reset_time: string;
  timezone: string;
  thresholds: number[];
};

export type AccountsReport = {
  accounts: AccountOption[];
  snapshots: AuthSnapshot[];
  attribution?: AttributionReport | null;
  auto_account_limit_defaults?: AutoAccountLimitDefaults;
};

export type DaysReport = {
  period: { from: string; to: string };
  days: UsageDay[];
  weeks?: UsageDay[];
  months?: UsageDay[];
  exchange_rate: { rate: number; source: string; day: string };
  cache?: CacheMeta;
};

export type SessionHistoryReport = {
  generated_at?: string;
  period: { from: string; to: string };
  source_roots?: string[];
  files_scanned?: number;
  usage_events?: number;
  totals: UsageTotals;
  sessions: SessionSummary[];
  top_sessions?: SessionSummary[];
  by_project?: SessionProjectRow[];
  account_switches?: AccountSwitchEvent[];
  cache_report?: SessionCacheReport;
  warnings?: string[];
  pricing_metadata?: PricingMetadata;
  currency?: { code?: string; usd_zar?: number };
  exchange_rate?: { rate: number; source: string; day: string };
  accounts?: string[];
  cache?: CacheMeta;
};

export type Budget = {
  period: "today" | "week" | "month";
  start: string;
  end: string;
  budget_zar: number;
  current_zar: number;
  budget_credits: number;
  current_credits: number;
  unit: "credits" | "zar";
  ratio: number;
  exceeded: boolean;
};

export type AccountLimitStatus = {
  id: number;
  account: string;
  metric: "total_tokens" | "total_credits";
  cap_value: number;
  current_value: number;
  ratio: number;
  remaining_value: number;
  window_start: string;
  window_end: string;
  window_start_at: string;
  window_end_at: string;
  reset_at: string;
  reset_weekday: number;
  reset_time: string;
  timezone: string;
  thresholds: number[];
  crossed_thresholds: number[];
  next_threshold?: number | null;
  exceeded: boolean;
  enabled: boolean;
  elapsed_days: number;
  remaining_days: number;
  safe_daily_spend: number;
  spend_rate_vs_target: number;
  projected_exhaustion_date?: string | null;
  projected_exhaustion_label: string;
  burn_severity: "ok" | "info" | "warning" | "critical";
  burn_advisories: Array<{
    id: string;
    severity: "info" | "warning" | "critical";
    message: string;
    label: string;
    value: string;
  }>;
};

export type AccountLimit = {
  id?: number;
  account: string;
  metric: "total_tokens" | "total_credits";
  cap_value: number;
  reset_weekday: number;
  reset_time: string;
  timezone: string;
  thresholds: string | number[];
  enabled: number | boolean;
  created_at?: string;
  updated_at?: string;
};

export type AccountLimitsReport = {
  limits: AccountLimit[];
  statuses: AccountLimitStatus[];
  status_state?: "ready" | "warming" | "refreshing" | string;
};

export type AuthSnapshotCreate = {
  observed_at?: string;
  account_id?: string;
  email?: string;
  name?: string;
  source?: string;
};

export type AuthSnapshotResult = {
  inserted: boolean;
  snapshot: AuthSnapshotCreate;
};

export type ChangelogGroup = {
  name: string;
  items: string[];
};

export type ChangelogRelease = {
  version?: string | null;
  date?: string | null;
  title: string;
  groups: ChangelogGroup[];
};

export type ChangelogReport = {
  generated_at: string;
  source: string;
  releases: ChangelogRelease[];
  unreleased?: ChangelogRelease | null;
};

export type UpdateStatus = {
  state: "up_to_date" | "update_available" | "checking_failed" | "unavailable" | "updating" | "update_failed" | string;
  generated_at: string;
  checked_at?: string | null;
  current_version?: string | null;
  running_version?: string | null;
  latest_version?: string | null;
  latest_tag?: string | null;
  install_mode?: string | null;
  remote?: string | null;
  check_mode?: string | null;
  source_url?: string | null;
  manual_update_command?: string | null;
  message?: string | null;
  error?: string | null;
  stale?: boolean;
};

export type Snapshot = {
  version?: string;
  generated_at: string;
  timezone?: string;
  status?: string;
  error?: string | null;
  reports?: {
    today?: UsageReport;
    week?: UsageReport;
    month?: UsageReport;
  } | null;
  budgets?: Budget[] | null;
  alerts_emitted?: Alert[];
  account_limits?: AccountLimitStatus[];
  update_reason?: string | null;
  cache?: SnapshotCacheStatus;
};

export type Settings = Record<
  | "daily_budget_zar"
  | "weekly_budget_zar"
  | "monthly_budget_zar"
  | "pricing_mode"
  | "usd_zar_fallback_rate"
  | "webhook_url"
  | "webhook_ui_enabled"
  | "dashboard_url"
  | "dashboard_mode"
  | "ui_theme"
  | "unknown_account_mapping"
  | "session_high_input_tokens"
  | "session_high_uncached_input_tokens"
  | "session_low_cache_min_uncached_tokens"
  | "session_low_cache_max_reuse_ratio"
  | "session_large_total_tokens"
  | "session_high_output_tokens"
  | "session_long_context_pricing_signal_enabled",
  string
>;

export type Alert = {
  id: number;
  created_at: string;
  type?: "budget_alert" | "account_limit_alert" | "account_burn_alert" | string;
  period?: string;
  budget_zar?: number;
  current_zar?: number;
  budget_credits?: number;
  current_credits?: number;
  unit?: "credits" | "zar";
  account?: string;
  metric?: string;
  threshold_ratio?: number;
  cap_value?: number;
  current_value?: number;
  remaining_value?: number;
  severity?: "info" | "warning" | "critical" | string;
  advisory_id?: string;
  message?: string;
  label?: string;
  value?: string;
  window_start?: string;
  window_end?: string;
  projected_exhaustion_date?: string | null;
  projected_exhaustion_label?: string;
  safe_daily_spend?: number;
  spend_rate_vs_target?: number;
};

export type RateCard = {
  unit: string;
  source?: string;
  updated?: string;
  fast_mode_detectable: boolean;
  fast_mode_note: string;
  rows: Array<{
    model: string;
    input_credits: number;
    cached_input_credits: number;
    output_credits: number;
    source?: string;
  }>;
};

export type DateRange = {
  start_at: string;
  end_at: string;
};
