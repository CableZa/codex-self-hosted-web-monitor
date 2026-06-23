import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it, vi } from "vitest";
import type { AccountLimitStatus, AccountsReport, DateRange, SessionHistoryReport, UsageReport } from "../lib/apiTypes";
import { DashboardTab } from "./DashboardTab";

const range: DateRange = {
  start_at: "2026-06-01T00:00:00+00:00",
  end_at: "2026-06-02T00:00:00+00:00",
};

const totals = {
  input_tokens: 0,
  cached_input_tokens: 0,
  output_tokens: 0,
  reasoning_output_tokens: 0,
  total_tokens: 0,
  total_usd: 0,
  total_zar: 0,
  input_credits: 0,
  cached_input_credits: 0,
  output_credits: 0,
  reasoning_output_credits: 0,
  total_credits: 0,
};

const summary: UsageReport = {
  period: { from: range.start_at, to: range.end_at },
  totals,
  by_day: [],
  by_model: [],
  by_effort: [],
  by_account: [],
  by_day_model: [],
  by_day_account: [],
  by_model_effort: [],
  exchange_rate: { rate: 18.5, source: "disabled", day: "2026-06-01" },
};

const accounts: AccountsReport = {
  accounts: [
    {
      account: "work@example.com",
      email: "work@example.com",
      source: "codex_auth",
      first_seen: "2026-06-01T10:00:00+00:00",
      last_seen: "2026-06-03T10:00:00+00:00",
    },
  ],
  snapshots: [
    {
      observed_at: "2026-06-03T10:00:00+00:00",
      email: "work@example.com",
      source: "codex_auth",
    },
  ],
};

const sessions: SessionHistoryReport = {
  period: { from: range.start_at, to: range.end_at },
  totals,
  sessions: [],
};

const thinRunwayStatus: AccountLimitStatus = {
  id: 1,
  account: "work@example.com",
  metric: "total_credits",
  cap_value: 700,
  current_value: 300,
  ratio: 0.43,
  remaining_value: 400,
  window_start: "2026-06-01",
  window_end: "2026-06-07",
  window_start_at: "2026-06-01T10:00:00+00:00",
  window_end_at: "2026-06-07T10:00:00+00:00",
  reset_at: "2026-06-07T10:00:00+00:00",
  reset_weekday: 0,
  reset_time: "10:00",
  elapsed_days: 4,
  remaining_days: 3,
  safe_daily_spend: 133.33,
  spend_rate_vs_target: 1.2,
  projected_exhaustion_date: null,
  projected_exhaustion_label: "Not projected this window",
  crossed_thresholds: [],
  next_threshold: 0.7,
  thresholds: [0.7, 0.85, 0.95, 1],
  timezone: "UTC",
  enabled: true,
  exceeded: false,
  burn_severity: "warning",
  burn_advisories: [
    {
      id: "thin-runway",
      severity: "warning",
      message: "400 credits left across 3 days.",
      label: "Safe daily pace",
      value: "133.33 credits/day",
    },
  ],
};

function installLocalStorage() {
  const values = new Map<string, string>();
  vi.stubGlobal("window", {
    localStorage: {
      getItem: (key: string) => values.get(key) ?? null,
      setItem: (key: string, value: string) => values.set(key, value),
    },
  });
}

describe("DashboardTab", () => {
  it("renders focused account attention, overview, and limits sections", () => {
    installLocalStorage();

    const html = renderToStaticMarkup(
      <DashboardTab
        accountLimitStatuses={[]}
        accounts={accounts}
        accountsLoading={false}
        alerts={[]}
        alertsFetching={false}
        alertsLoading={false}
        applyAccounts={() => undefined}
        applyChartMode={() => undefined}
        applyGroupMode={() => undefined}
        applyRange={() => undefined}
        chartMode="bar"
        days={{ period: { from: range.start_at, to: range.end_at }, days: [], exchange_rate: summary.exchange_rate }}
        daysFetching={false}
        daysLoading
        draftRange={range}
        focusedMode={false}
        groupMode="day"
        groupedRows={[]}
        range={range}
        rangeError=""
        selectedAccounts={[]}
        selectedTotals={totals}
        setDraftRange={() => undefined}
        sessions={sessions}
        sessionsFetching={false}
        sessionsPlaceholder={false}
        signalThresholds={{
          highInputTokens: 1000000,
          highUncachedInputTokens: 500000,
          lowCacheMinUncachedTokens: 100000,
          lowCacheMaxReuseRatio: 0.5,
          largeTotalTokens: 1000000,
          highOutputTokens: 50000,
          longContextPricingSignalEnabled: true,
        }}
        onOpenSettings={() => undefined}
        snapshot={{ generated_at: "2026-06-03T10:00:00+00:00", timezone: "UTC" }}
        snapshotLoading={false}
        summary={summary}
        summaryFetching={false}
        summaryLoading
        timezone="UTC"
      />,
    );

    expect(html).toContain("Needs attention");
    expect(html).toContain("work@example.com has no weekly credit limit");
    expect(html).toContain("Codex Credit Usage");
    expect(html).toContain("Cost drivers");
    expect(html).toContain("Codex Limits");
  });

  it("renders thin-runway burn advice as a daily pace", () => {
    installLocalStorage();

    const html = renderToStaticMarkup(
      <DashboardTab
        accountLimitStatuses={[thinRunwayStatus]}
        accounts={accounts}
        accountsLoading={false}
        alerts={[]}
        alertsFetching={false}
        alertsLoading={false}
        applyAccounts={() => undefined}
        applyChartMode={() => undefined}
        applyGroupMode={() => undefined}
        applyRange={() => undefined}
        chartMode="bar"
        days={{ period: { from: range.start_at, to: range.end_at }, days: [], exchange_rate: summary.exchange_rate }}
        daysFetching={false}
        daysLoading={false}
        draftRange={range}
        focusedMode={false}
        groupMode="day"
        groupedRows={[]}
        range={range}
        rangeError=""
        selectedAccounts={[]}
        selectedTotals={totals}
        setDraftRange={() => undefined}
        sessions={sessions}
        sessionsFetching={false}
        sessionsPlaceholder={false}
        signalThresholds={{
          highInputTokens: 1000000,
          highUncachedInputTokens: 500000,
          lowCacheMinUncachedTokens: 100000,
          lowCacheMaxReuseRatio: 0.5,
          largeTotalTokens: 1000000,
          highOutputTokens: 50000,
          longContextPricingSignalEnabled: true,
        }}
        onOpenSettings={() => undefined}
        snapshot={{ generated_at: "2026-06-03T10:00:00+00:00", timezone: "UTC" }}
        snapshotLoading={false}
        summary={summary}
        summaryFetching={false}
        summaryLoading={false}
        timezone="UTC"
      />,
    );

    expect(html).toContain("Safe daily pace: 133.33 credits/day");
    expect(html).toContain("work@example.com · 400 credits left across 3 days.");
  });
});
