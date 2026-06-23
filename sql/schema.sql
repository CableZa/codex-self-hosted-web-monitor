pragma foreign_keys = on;

create table if not exists schema_migrations (
  version integer primary key,
  applied_at text not null
);

create table if not exists settings (
  key text primary key,
  value text not null
);

create table if not exists alerts (
  id integer primary key autoincrement,
  created_at text not null,
  period text not null,
  period_start text not null,
  period_end text not null,
  threshold_ratio real not null,
  budget_zar real not null,
  current_zar real not null,
  budget_credits real not null default 0,
  current_credits real not null default 0,
  unit text not null default 'zar',
  payload text not null
);

create index if not exists idx_alerts_period_bounds_threshold
  on alerts(period, period_start, period_end, threshold_ratio);

create index if not exists idx_alerts_id_desc
  on alerts(id desc);

create table if not exists summaries (
  id integer primary key autoincrement,
  created_at text not null,
  summary_for text not null,
  slot text not null,
  payload text not null,
  unique(summary_for, slot)
);

create index if not exists idx_summaries_summary_for_slot
  on summaries(summary_for, slot);

create table if not exists fx_rates (
  day text primary key,
  usd_zar real not null,
  source text not null,
  fetched_at text not null
);

create table if not exists auth_snapshots (
  id integer primary key autoincrement,
  observed_at text not null,
  account_id text,
  email text,
  name text,
  source text not null
);

create index if not exists idx_auth_snapshots_observed_at
  on auth_snapshots(observed_at);

create index if not exists idx_auth_snapshots_account
  on auth_snapshots(email, account_id);

create table if not exists account_usage_limits (
  id integer primary key autoincrement,
  account text not null unique,
  metric text not null default 'total_tokens',
  cap_value real not null,
  reset_weekday integer not null default 4,
  reset_time text not null default '00:00',
  timezone text not null default 'UTC',
  thresholds text not null default '[0.7,0.85,0.95,1.0]',
  enabled integer not null default 1,
  created_at text not null,
  updated_at text not null
);

create index if not exists idx_account_usage_limits_enabled
  on account_usage_limits(enabled, account);

create table if not exists account_limit_alerts (
  id integer primary key autoincrement,
  created_at text not null,
  account text not null,
  metric text not null,
  window_start text not null,
  window_end text not null,
  threshold_ratio real not null,
  payload text not null,
  unique(account, metric, window_start, window_end, threshold_ratio)
);

create index if not exists idx_account_limit_alerts_lookup
  on account_limit_alerts(account, metric, window_start, window_end, threshold_ratio);

create table if not exists account_burn_alerts (
  id integer primary key autoincrement,
  created_at text not null,
  account text not null,
  advisory_id text not null,
  severity text not null,
  window_start text not null,
  window_end text not null,
  payload text not null,
  unique(account, advisory_id, severity, window_start, window_end)
);

create index if not exists idx_account_burn_alerts_lookup
  on account_burn_alerts(account, advisory_id, severity, window_start, window_end);

create table if not exists usage_daily_aggregate_days (
  cache_version text not null,
  day text not null,
  generated_at text not null,
  warnings text not null default '[]',
  primary key(cache_version, day)
);

create table if not exists usage_daily_aggregates (
  cache_version text not null,
  day text not null,
  account text not null,
  model text not null,
  effort text not null,
  input_tokens integer not null default 0,
  cached_input_tokens integer not null default 0,
  output_tokens integer not null default 0,
  reasoning_output_tokens integer not null default 0,
  total_tokens integer not null default 0,
  input_usd real not null default 0,
  cached_input_usd real not null default 0,
  output_usd real not null default 0,
  reasoning_output_usd real not null default 0,
  total_usd real not null default 0,
  input_credits real not null default 0,
  cached_input_credits real not null default 0,
  output_credits real not null default 0,
  reasoning_output_credits real not null default 0,
  total_credits real not null default 0,
  long_context_applied integer not null default 0,
  events integer not null default 0,
  sessions text not null default '[]',
  files text not null default '[]',
  primary key(cache_version, day, account, model, effort)
);

create index if not exists idx_usage_daily_aggregates_lookup
  on usage_daily_aggregates(cache_version, day, account);
