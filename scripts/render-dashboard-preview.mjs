import { mkdir } from "node:fs/promises";
import { dirname, resolve } from "node:path";
import { chromium } from "playwright";
import { createServer } from "vite";

const outputPath = resolve("docs/assets/dashboard-preview.png");
const range = {
  start_at: "2026-06-01T00:00",
  end_at: "2026-06-15T00:00",
};
const generatedAt = "2026-06-14T15:30:00+00:00";
const exchangeRate = { rate: 18.5, source: "disabled", day: "2026-06-14" };

function totals(values = {}) {
  const input = values.input_tokens ?? (values.uncached_input_tokens || 0) + (values.cached_input_tokens || 0);
  const cached = values.cached_input_tokens || 0;
  const uncached = values.uncached_input_tokens ?? Math.max(0, input - cached);
  const output = values.output_tokens || 0;
  const reasoning = values.reasoning_output_tokens || 0;
  const totalTokens = values.total_tokens ?? input + output + reasoning;
  const inputCredits = values.input_credits ?? uncached * 0.0018;
  const cachedCredits = values.cached_input_credits ?? cached * 0.00018;
  const outputCredits = values.output_credits ?? output * 0.008;
  const reasoningCredits = values.reasoning_output_credits ?? reasoning * 0.004;
  const totalCredits = values.total_credits ?? inputCredits + cachedCredits + outputCredits + reasoningCredits;
  const totalUsd = values.total_usd ?? totalCredits * 0.0001;
  return {
    input_tokens: Math.round(input),
    cached_input_tokens: Math.round(cached),
    uncached_input_tokens: Math.round(uncached),
    output_tokens: Math.round(output),
    reasoning_output_tokens: Math.round(reasoning),
    total_tokens: Math.round(totalTokens),
    input_usd: inputCredits * 0.0001,
    cached_input_usd: cachedCredits * 0.0001,
    output_usd: outputCredits * 0.0001,
    reasoning_output_usd: reasoningCredits * 0.0001,
    total_usd: totalUsd,
    total_zar: totalUsd * exchangeRate.rate,
    input_credits: inputCredits,
    cached_input_credits: cachedCredits,
    output_credits: outputCredits,
    reasoning_output_credits: reasoningCredits,
    total_credits: totalCredits,
    long_context_applied: Boolean(values.long_context_applied),
    long_context_events: values.long_context_events || 0,
    max_input_tokens: values.max_input_tokens || Math.round(input),
    cache_hit_ratio: input ? cached / input : 0,
    events: values.events || 0,
    sessions: values.sessions || 0,
    files: values.files || 0,
  };
}

function addTotals(rows) {
  return rows.reduce((sum, row) => totals({
    input_tokens: sum.input_tokens + row.input_tokens,
    cached_input_tokens: sum.cached_input_tokens + row.cached_input_tokens,
    uncached_input_tokens: sum.uncached_input_tokens + row.uncached_input_tokens,
    output_tokens: sum.output_tokens + row.output_tokens,
    reasoning_output_tokens: sum.reasoning_output_tokens + row.reasoning_output_tokens,
    total_tokens: sum.total_tokens + row.total_tokens,
    input_credits: sum.input_credits + row.input_credits,
    cached_input_credits: sum.cached_input_credits + row.cached_input_credits,
    output_credits: sum.output_credits + row.output_credits,
    reasoning_output_credits: sum.reasoning_output_credits + row.reasoning_output_credits,
    total_credits: sum.total_credits + row.total_credits,
    total_usd: sum.total_usd + row.total_usd,
    events: sum.events + row.events,
    sessions: sum.sessions + row.sessions,
    files: sum.files + row.files,
  }), totals());
}

function usageDay(day, index) {
  const uncached = 180_000 + index * 12_500 + (index % 3) * 32_000;
  const cached = 460_000 + index * 28_000 + (index % 4) * 54_000;
  const output = 38_000 + index * 3_400 + (index % 2) * 9_500;
  const row = totals({
    uncached_input_tokens: uncached,
    cached_input_tokens: cached,
    output_tokens: output,
    events: 22 + index,
    sessions: 4 + (index % 5),
    files: 2,
    long_context_applied: index === 8,
    long_context_events: index === 8 ? 1 : 0,
  });
  return { day, ...row };
}

function scaleTotals(base, factor, extra = {}) {
  return {
    ...totals({
      input_tokens: base.input_tokens * factor,
      cached_input_tokens: base.cached_input_tokens * factor,
      uncached_input_tokens: base.uncached_input_tokens * factor,
      output_tokens: base.output_tokens * factor,
      reasoning_output_tokens: base.reasoning_output_tokens * factor,
      total_tokens: base.total_tokens * factor,
      input_credits: base.input_credits * factor,
      cached_input_credits: base.cached_input_credits * factor,
      output_credits: base.output_credits * factor,
      reasoning_output_credits: base.reasoning_output_credits * factor,
      total_credits: base.total_credits * factor,
      total_usd: base.total_usd * factor,
      events: Math.round(base.events * factor),
      sessions: Math.round(base.sessions * factor),
      files: Math.max(1, Math.round(base.files * factor)),
    }),
    ...extra,
  };
}

const days = Array.from({ length: 14 }, (_, index) => {
  const day = String(index + 1).padStart(2, "0");
  return usageDay(`2026-06-${day}`, index);
});
const reportTotals = addTotals(days);
const byAccount = [
  scaleTotals(reportTotals, 0.66, { account: "work@example.com" }),
  scaleTotals(reportTotals, 0.34, { account: "team@example.org" }),
];
const byModel = [
  scaleTotals(reportTotals, 0.52, { model: "gpt-5.5" }),
  scaleTotals(reportTotals, 0.31, { model: "gpt-5.4-mini" }),
  scaleTotals(reportTotals, 0.17, { model: "gpt-5.3-codex" }),
];
const byEffort = [
  scaleTotals(reportTotals, 0.58, { effort: "high" }),
  scaleTotals(reportTotals, 0.29, { effort: "medium" }),
  scaleTotals(reportTotals, 0.13, { effort: "low" }),
];

function usageReport(dayRows = days) {
  return {
    generated_at: generatedAt,
    period: { from: range.start_at, to: range.end_at },
    source_roots: ["~/.codex/sessions", "~/.codex/archived_sessions"],
    files_scanned: 28,
    usage_events: reportTotals.events,
    totals: addTotals(dayRows),
    by_day: dayRows,
    by_week: [{ day: "2026-06-01", label: "2026-06-01 to 2026-06-07", ...addTotals(dayRows.slice(0, 7)) }],
    by_month: [{ day: "2026-06", label: "2026-06", ...addTotals(dayRows) }],
    by_model: byModel,
    by_effort: byEffort,
    by_account: byAccount,
    by_day_model: [],
    by_day_account: [],
    by_model_effort: [],
    exchange_rate: exchangeRate,
    currency: { code: "ZAR", usd_zar: exchangeRate.rate },
    accounts: ["work@example.com", "team@example.org"],
    cache: { hit: true, ttl_seconds: 300, served_at: generatedAt },
    warnings: [],
    pricing_metadata: {
      currency: "credits",
      unit: "credits",
      updated: "2026-06-01",
      credit_unit: "codex_credit",
      credit_source: "demo",
      notes: [],
    },
  };
}

const accountLimitStatuses = [
  {
    id: 1,
    account: "work@example.com",
    metric: "total_credits",
    cap_value: 18_000,
    current_value: 13_950,
    ratio: 0.775,
    remaining_value: 4_050,
    window_start: "2026-06-08",
    window_end: "2026-06-15",
    window_start_at: "2026-06-08T10:00:00+00:00",
    window_end_at: "2026-06-15T10:00:00+00:00",
    reset_at: "2026-06-15T10:00:00+00:00",
    reset_weekday: 1,
    reset_time: "10:00",
    timezone: "UTC",
    thresholds: [0.7, 0.85, 0.95, 1],
    crossed_thresholds: [0.7],
    next_threshold: 0.85,
    exceeded: false,
    enabled: true,
    elapsed_days: 6,
    remaining_days: 1,
    safe_daily_spend: 4050,
    spend_rate_vs_target: 1.4,
    projected_exhaustion_date: null,
    projected_exhaustion_label: "Not projected this window",
    burn_severity: "warning",
    burn_advisories: [{
      id: "thin-runway",
      severity: "warning",
      message: "4.1K credits left with 1 day remaining.",
      label: "Safe daily pace",
      value: "4.1K credits/day",
    }],
  },
  {
    id: 2,
    account: "team@example.org",
    metric: "total_credits",
    cap_value: 14_000,
    current_value: 6_800,
    ratio: 0.486,
    remaining_value: 7_200,
    window_start: "2026-06-08",
    window_end: "2026-06-15",
    window_start_at: "2026-06-08T10:00:00+00:00",
    window_end_at: "2026-06-15T10:00:00+00:00",
    reset_at: "2026-06-15T10:00:00+00:00",
    reset_weekday: 1,
    reset_time: "10:00",
    timezone: "UTC",
    thresholds: [0.7, 0.85, 0.95, 1],
    crossed_thresholds: [],
    next_threshold: 0.7,
    exceeded: false,
    enabled: true,
    elapsed_days: 6,
    remaining_days: 1,
    safe_daily_spend: 7200,
    spend_rate_vs_target: 0.8,
    projected_exhaustion_date: null,
    projected_exhaustion_label: "Not projected this window",
    burn_severity: "ok",
    burn_advisories: [],
  },
];

const sessions = [
  {
    session_id: "demo-session-a",
    first_seen: "2026-06-14T09:10:00+00:00",
    last_seen: "2026-06-14T10:45:00+00:00",
    duration_seconds: 5700,
    display_title: "Tighten dashboard preview generation",
    first_message: "Build a real dashboard preview from mocked API data",
    last_message: "Verify the screenshot workflow",
    summary: "Rendered the dashboard against deterministic demo data.",
    project_name: "codex-web-monitor",
    project_path: "/repo/codex-web-monitor",
    cache_efficiency: 0.42,
    long_context: true,
    long_context_reasons: ["Large project context"],
    accounts: ["work@example.com"],
    efforts: ["high"],
    user_message_count: 8,
    first_message_word_count: 9,
    tool_call_count: 18,
    tool_error_count: 1,
    max_consecutive_tool_errors: 1,
    repeated_tool_signatures: 2,
    web_tool_call_count: 0,
    large_ingest_count: 1,
    waste_findings: [],
    estimated_waste_credits: 220,
    estimated_waste_usd: 0.022,
    efficiency_score: 74,
    efficiency_grade: "B",
    by_model: [scaleTotals(reportTotals, 0.08, { model: "gpt-5.5" })],
    ...totals({ uncached_input_tokens: 720_000, cached_input_tokens: 520_000, output_tokens: 96_000, events: 36, sessions: 1, files: 2 }),
  },
  {
    session_id: "demo-session-b",
    first_seen: "2026-06-13T13:20:00+00:00",
    last_seen: "2026-06-13T14:05:00+00:00",
    duration_seconds: 2700,
    display_title: "Review account limit copy",
    first_message: "Review the account limit panel",
    last_message: "Ship the safer copy",
    summary: "Adjusted labels and checked responsive states.",
    project_name: "codex-web-monitor",
    project_path: "/repo/codex-web-monitor",
    cache_efficiency: 0.74,
    long_context: false,
    accounts: ["team@example.org"],
    efforts: ["medium"],
    user_message_count: 5,
    tool_call_count: 8,
    tool_error_count: 0,
    max_consecutive_tool_errors: 0,
    repeated_tool_signatures: 0,
    web_tool_call_count: 0,
    large_ingest_count: 0,
    waste_findings: [],
    estimated_waste_credits: 0,
    estimated_waste_usd: 0,
    efficiency_score: 91,
    efficiency_grade: "A",
    by_model: [scaleTotals(reportTotals, 0.04, { model: "gpt-5.4-mini" })],
    ...totals({ uncached_input_tokens: 180_000, cached_input_tokens: 530_000, output_tokens: 42_000, events: 18, sessions: 1, files: 1 }),
  },
];

const sessionReport = {
  generated_at: generatedAt,
  period: { from: range.start_at, to: range.end_at },
  source_roots: ["~/.codex/sessions"],
  files_scanned: 28,
  usage_events: reportTotals.events,
  totals: reportTotals,
  sessions,
  top_sessions: sessions,
  by_project: [
    scaleTotals(reportTotals, 0.71, { project: "codex-web-monitor", project_path: "/repo/codex-web-monitor" }),
    scaleTotals(reportTotals, 0.29, { project: "release-tools", project_path: "/repo/release-tools" }),
  ],
  account_switches: [{
    observed_at: "2026-06-12T08:00:00+00:00",
    from_account: "team@example.org",
    to_account: "work@example.com",
    source: "codex_auth",
  }],
  cache_report: {
    cache_efficiency: 0.68,
    cached_input_tokens: reportTotals.cached_input_tokens,
    uncached_input_tokens: reportTotals.uncached_input_tokens,
    inefficient_sessions: 1,
  },
  warnings: [],
  pricing_metadata: usageReport().pricing_metadata,
  currency: { code: "ZAR", usd_zar: exchangeRate.rate },
  exchange_rate: exchangeRate,
  accounts: ["work@example.com", "team@example.org"],
  cache: { hit: true, ttl_seconds: 300, served_at: generatedAt },
};

const accounts = {
  accounts: [
    {
      account: "work@example.com",
      email: "work@example.com",
      name: "Work Account",
      source: "codex_auth",
      first_seen: "2026-06-01T08:00:00+00:00",
      last_seen: "2026-06-14T15:15:00+00:00",
    },
    {
      account: "team@example.org",
      email: "team@example.org",
      name: "Team Account",
      source: "codex_auth",
      first_seen: "2026-06-01T08:00:00+00:00",
      last_seen: "2026-06-13T14:05:00+00:00",
    },
  ],
  snapshots: [
    { id: 1, observed_at: "2026-06-01T08:00:00+00:00", email: "team@example.org", source: "codex_auth" },
    { id: 2, observed_at: "2026-06-14T15:15:00+00:00", email: "work@example.com", source: "codex_auth" },
  ],
  attribution: {
    history: {
      earliest_usage_day: "2026-06-01",
      latest_usage_day: "2026-06-14",
      first_auth_snapshot_at: "2026-06-01T08:00:00+00:00",
      visible_rollout_files: 28,
      sessions_root_files: 24,
      archived_sessions_root_files: 4,
    },
    issues: [],
  },
  auto_account_limit_defaults: {
    email_suffixes: ["@example.com", "@example.org"],
    cap_credits: 18_000,
    reset_weekday: 1,
    reset_time: "10:00",
    timezone: "UTC",
    thresholds: [0.7, 0.85, 0.95, 1],
  },
};

const settings = {
  daily_budget_zar: "0",
  weekly_budget_zar: "0",
  monthly_budget_zar: "0",
  pricing_mode: "credits",
  usd_zar_fallback_rate: "18.5",
  webhook_url: "",
  webhook_ui_enabled: "false",
  dashboard_url: "http://127.0.0.1:18787",
  dashboard_mode: "standard",
  ui_theme: "catppuccin",
  unknown_account_mapping: "",
  session_high_input_tokens: "1000000",
  session_high_uncached_input_tokens: "500000",
  session_low_cache_min_uncached_tokens: "100000",
  session_low_cache_max_reuse_ratio: "0.5",
  session_large_total_tokens: "1000000",
  session_high_output_tokens: "50000",
  session_long_context_pricing_signal_enabled: "true",
};

const mocks = {
  "/api/snapshot": {
    version: "0.17.0",
    generated_at: generatedAt,
    timezone: "UTC",
    reports: {
      today: usageReport(days.slice(-1)),
      week: usageReport(days.slice(-7)),
      month: usageReport(days),
    },
    budgets: [
      {
        period: "week",
        start: "2026-06-08",
        end: "2026-06-15",
        budget_zar: 0,
        current_zar: reportTotals.total_zar,
        budget_credits: 20_000,
        current_credits: 13_950,
        unit: "credits",
        ratio: 0.6975,
        exceeded: false,
      },
    ],
    account_limits: accountLimitStatuses,
    alerts_emitted: [],
    cache: {
      ok: true,
      backend: { backend: "valkey", ok: true, key_prefix: "monitor" },
      response: { hit: true, ttl_seconds: 300, served_at: generatedAt },
    },
  },
  "/api/settings": settings,
  "/api/rate-card": {
    unit: "credits",
    source: "demo",
    updated: "2026-06-01",
    fast_mode_detectable: true,
    fast_mode_note: "Fast mode appears as lower effort usage in Codex logs.",
    rows: [
      { model: "gpt-5.5", input_credits: 5, cached_input_credits: 0.5, output_credits: 30 },
      { model: "gpt-5.4-mini", input_credits: 0.75, cached_input_credits: 0.075, output_credits: 4.5 },
    ],
  },
  "/api/days": {
    period: { from: range.start_at, to: range.end_at },
    days,
    weeks: usageReport().by_week,
    months: usageReport().by_month,
    exchange_rate: exchangeRate,
    cache: { hit: true, ttl_seconds: 300, served_at: generatedAt },
  },
  "/api/summary": usageReport(),
  "/api/sessions": sessionReport,
  "/api/accounts": accounts,
  "/api/account-limits": {
    limits: accountLimitStatuses.map((status) => ({
      id: status.id,
      account: status.account,
      metric: status.metric,
      cap_value: status.cap_value,
      reset_weekday: status.reset_weekday,
      reset_time: status.reset_time,
      timezone: status.timezone,
      thresholds: status.thresholds,
      enabled: status.enabled,
    })),
    statuses: accountLimitStatuses,
    status_state: "ready",
  },
  "/api/update-status": {
    state: "up_to_date",
    generated_at: generatedAt,
    checked_at: generatedAt,
    current_version: "0.17.0",
    running_version: "0.17.0",
    latest_version: "0.17.0",
    latest_tag: "v0.17.0",
    install_mode: "docker",
    remote: "origin",
    check_mode: "stable",
    message: "Running the latest stable release.",
    stale: false,
  },
  "/api/alerts": [
    {
      id: 101,
      created_at: "2026-06-14T14:55:00+00:00",
      type: "account_burn_alert",
      account: "work@example.com",
      metric: "total_credits",
      severity: "warning",
      advisory_id: "thin-runway",
      message: "Safe daily pace is tight",
      label: "Safe daily pace",
      value: "4.1K credits/day",
      current_value: 13_950,
      cap_value: 18_000,
      remaining_value: 4_050,
      window_start: "2026-06-08",
      window_end: "2026-06-15",
      projected_exhaustion_date: null,
      projected_exhaustion_label: "Not projected this window",
      safe_daily_spend: 4050,
      spend_rate_vs_target: 1.4,
    },
  ],
  "/api/changelog": {
    generated_at: generatedAt,
    source: "CHANGELOG.md",
    releases: [{
      version: "0.17.0",
      date: "2026-06-23",
      title: "v0.17.0",
      groups: [{ name: "Added", items: ["Dashboard update notices"] }],
    }],
  },
};

async function routeApi(route) {
  const url = new URL(route.request().url());
  if (url.pathname === "/api/events") {
    await route.fulfill({
      status: 200,
      headers: { "content-type": "text/event-stream; charset=utf-8" },
      body: ": preview stream ready\n\n",
    });
    return;
  }
  if (url.pathname.startsWith("/api/sessions/")) {
    await route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify({ ...sessions[0], timeline: [] }) });
    return;
  }
  const payload = mocks[url.pathname];
  if (!payload) {
    await route.fulfill({ status: 404, contentType: "text/plain", body: `No preview mock for ${url.pathname}` });
    return;
  }
  await route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify(payload) });
}

const server = await createServer({ configFile: resolve("vite.config.ts"), server: { host: "127.0.0.1", port: 0 } });
let browser;

try {
  await server.listen();
  const address = server.httpServer?.address();
  const port = typeof address === "object" && address ? address.port : 5173;
  browser = await chromium.launch();
  const page = await browser.newPage({ viewport: { width: 1280, height: 1120 }, deviceScaleFactor: 1 });
  await page.route("**/api/**", routeApi);
  await page.addInitScript(() => {
    window.localStorage.clear();
  });
  const params = new URLSearchParams({ tab: "dashboard", start_at: range.start_at, end_at: range.end_at, group: "day", chart: "bar" });
  await page.goto(`http://127.0.0.1:${port}/static/?${params.toString()}`, { waitUntil: "networkidle" });
  await page.getByText("Codex Credit Usage").waitFor({ timeout: 15_000 });
  await page.getByText("Codex Limits").waitFor({ timeout: 15_000 });
  await page.locator(".recharts-responsive-container svg").first().waitFor({ timeout: 15_000 });
  await mkdir(dirname(outputPath), { recursive: true });
  await page.screenshot({ path: outputPath });
  console.log(`Wrote ${outputPath}`);
} finally {
  if (browser) await browser.close();
  await server.close();
}
