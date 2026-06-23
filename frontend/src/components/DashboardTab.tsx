import { useState, type Dispatch, type SetStateAction } from "react";
import { Bell, Filter, LineChart as LineIcon, BarChart3, WalletCards } from "lucide-react";
import type {
  AccountLimitStatus,
  AccountOption,
  AccountsReport,
  Alert,
  DateRange,
  DaysReport,
  SessionHistoryReport,
  Snapshot,
  UpdateStatus,
  UsageReport,
  UsageTotals,
} from "../lib/apiTypes";
import {
  burnAdvisoriesForAccount,
  focusedMonitorAccount,
  latestObservedAccount,
  monitorAccountOptions,
  statusForAccount,
} from "../lib/accountMonitoring";
import type { ChartMode, GroupMode } from "../lib/dashboardState";
import { safeDailySpendForChart, weeklyBudgetWindow } from "../lib/dashboardSignals";
import type { SessionSignalThresholds } from "../lib/sessionSignalThresholds";
import type { Preset } from "../lib/dateRange";
import { cacheBackendLabel, type GroupedUsageDay } from "../lib/usage";
import { compactCredits, fmtRate, formatDateTime, formatLimitValue } from "../lib/format";
import { useLocalPreference } from "../lib/localPreference";
import { snapshotReport } from "../lib/snapshotState";
import { Panel } from "./Panel";
import { Spinner } from "./Spinner";
import { BudgetList, BreakdownTable } from "./DashboardTables";
import { CreditAreaChart, DashboardChart } from "./UsageCharts";
import { LoaderBlock } from "./DashboardPrimitives";
import { DashboardLimitsPanel } from "./DashboardLimitsPanel";
import { DashboardOverview } from "./DashboardOverview";
import { UsageWindowControls } from "./UsageWindowControls";
import { ActionCenter } from "./DashboardActionCenter";
import { MonitorAccountBar } from "./DashboardRunwayPanels";
import { DataWarning } from "./DataWarning";

const groupModes: Array<{ id: GroupMode; label: string }> = [
  { id: "day", label: "Daily" },
  { id: "week", label: "Weekly" },
  { id: "month", label: "Monthly" },
];

const chartModes: Array<{ id: ChartMode; label: string; icon: React.ReactNode }> = [
  { id: "bar", label: "Bars", icon: <BarChart3 className="h-4 w-4" /> },
  { id: "line", label: "Lines", icon: <LineIcon className="h-4 w-4" /> },
];

function includedEndDay(endAt: string) {
  const [day, time = ""] = endAt.split("T");
  if (time && time !== "00:00" && time !== "00:00:00") return day;
  const [year, month, date] = day.split("-").map(Number);
  if (!year || !month || !date) return day;
  return new Date(Date.UTC(year, month - 1, date - 1)).toISOString().slice(0, 10);
}

export function DashboardTab({
  accountLimitStatuses,
  accounts,
  accountsLoading,
  alerts,
  alertsFetching,
  alertsLoading,
  applyAccounts,
  applyChartMode,
  applyGroupMode,
  applyRange,
  chartMode,
  days,
  daysFetching,
  daysLoading,
  draftRange,
  focusedMode,
  groupMode,
  groupedRows,
  range,
  rangeError,
  selectedAccounts,
  selectedTotals,
  setDraftRange,
  sessions,
  sessionsFetching,
  sessionsPlaceholder,
  signalThresholds,
  onOpenSettings,
  snapshot,
  snapshotLoading,
  summary,
  summaryFetching,
  summaryLoading,
  timezone,
  updateStatus,
}: {
  accountLimitStatuses: AccountLimitStatus[];
  accounts?: AccountsReport;
  accountsLoading: boolean;
  alerts?: Alert[];
  alertsFetching: boolean;
  alertsLoading: boolean;
  applyAccounts: (accounts: string[]) => void;
  applyChartMode: (mode: ChartMode) => void;
  applyGroupMode: (mode: GroupMode) => void;
  applyRange: (range: DateRange, options?: { preset?: Preset }) => void;
  chartMode: ChartMode;
  days?: DaysReport;
  daysFetching: boolean;
  daysLoading: boolean;
  draftRange: DateRange;
  focusedMode: boolean;
  groupMode: GroupMode;
  groupedRows: GroupedUsageDay[];
  range: DateRange;
  rangeError: string;
  selectedAccounts: string[];
  selectedTotals: UsageTotals;
  setDraftRange: Dispatch<SetStateAction<DateRange>>;
  sessions?: SessionHistoryReport;
  sessionsFetching: boolean;
  sessionsPlaceholder: boolean;
  signalThresholds: SessionSignalThresholds;
  onOpenSettings: () => void;
  snapshot?: Snapshot;
  snapshotLoading: boolean;
  summary?: UsageReport;
  summaryFetching: boolean;
  summaryLoading: boolean;
  timezone: string;
  updateStatus?: UpdateStatus;
}) {
  const accountOptionsByName = new Map<string, AccountOption>();
  for (const option of accounts?.accounts || []) {
    accountOptionsByName.set(option.account, option);
  }
  for (const row of summary?.by_account || []) {
    if (row.account && !accountOptionsByName.has(row.account)) {
      accountOptionsByName.set(row.account, { account: row.account, source: "usage" });
    }
  }
  const accountOptions = Array.from(accountOptionsByName.values()).sort((left, right) => left.account.localeCompare(right.account));
  const singleAccount = accountOptions.length === 1 ? accountOptions[0] : null;
  const chartsBusy = daysLoading || daysFetching || summaryLoading || summaryFetching;
  const chartBusyClass = `transition-opacity duration-200 ${chartsBusy ? "opacity-35" : "opacity-100"}`;
  const todayReport = snapshotReport(snapshot, "today");
  const weekReport = snapshotReport(snapshot, "week");
  const monthReport = snapshotReport(snapshot, "month");
  const dataWarnings = Array.from(new Set([
    ...(todayReport?.warnings || []),
    ...(weekReport?.warnings || []),
    ...(monthReport?.warnings || []),
    ...(summary?.warnings || []),
  ])).filter(Boolean);
  const exchangeRate = todayReport?.exchange_rate;
  const exchangeRateLabel = exchangeRate
    ? exchangeRate.source === "disabled"
      ? `${fmtRate.format(exchangeRate.rate)} (live off)`
      : `${fmtRate.format(exchangeRate.rate)} (${exchangeRate.source})`
    : "loading";
  const budgetWindow = weeklyBudgetWindow(snapshot);
  const rangeStartDay = range.start_at.slice(0, 10);
  const rangeEndDay = includedEndDay(range.end_at);
  const chartRowsInsideBudgetWindow = Boolean(
    budgetWindow &&
    rangeStartDay >= budgetWindow.start &&
    rangeEndDay <= budgetWindow.end &&
    groupedRows.length &&
    groupedRows.every((row) => row.day >= budgetWindow.start && row.day <= budgetWindow.end),
  );
  const safeDailySpend = chartRowsInsideBudgetWindow ? safeDailySpendForChart(snapshot) : null;
  const sessionsFresh = Boolean(
    sessions &&
    !sessionsPlaceholder &&
    sessions.period.from === range.start_at &&
    sessions.period.to === range.end_at,
  );
  const [visibleSeries, setVisibleSeries] = useState({
    credits: true,
    uncached: true,
    cached: true,
    output: true,
  });
  const [monitorFocusOverride, setMonitorFocusOverride] = useLocalPreference("codex-monitor-focused-account", "");
  const activeAccount = latestObservedAccount(accounts);
  const monitorOptions = monitorAccountOptions(accounts, accountLimitStatuses);
  const focusedAccount = focusedMonitorAccount(accounts, accountLimitStatuses, monitorFocusOverride);
  const focusedStatus = statusForAccount(accountLimitStatuses, focusedAccount);
  const advisories = burnAdvisoriesForAccount(focusedStatus);
  const accountDetail = focusedAccount
    ? `Monitoring ${focusedAccount}`
    : selectedAccounts.length
      ? `${selectedAccounts.length} selected account${selectedAccounts.length === 1 ? "" : "s"}`
      : "All accounts";
  const overviewRangeLabel = `${rangeStartDay} to ${rangeEndDay}`;
  const overviewTotals = summary?.totals || selectedTotals;
  const accountFilterNode = singleAccount ? (
    <div className="inline-flex w-fit items-center gap-2 rounded-md border border-border bg-canvas/60 px-3 py-2 text-sm">
      <span className="text-muted">Account</span>
      <span className="font-semibold text-ink">{singleAccount.account}</span>
    </div>
  ) : !focusedMode ? (
    <div className="rounded-md border border-border bg-canvas/60 p-3">
      <div className="mb-2 flex flex-wrap items-center justify-between gap-2">
        <div className="inline-flex items-center gap-2 text-sm font-semibold">
          <Filter className="h-4 w-4 text-brand" />
          Accounts
        </div>
        <button
          type="button"
          className="text-sm font-semibold text-brand disabled:text-muted"
          disabled={!selectedAccounts.length}
          onClick={() => applyAccounts([])}
        >
          Show all
        </button>
      </div>
      {accountsLoading ? (
        <Spinner label="Loading accounts" />
      ) : accountOptions.length ? (
        <div className="flex flex-wrap gap-2">
          {accountOptions.map((option) => {
            const active = selectedAccounts.length === 0 || selectedAccounts.includes(option.account);
            const nextAccounts = selectedAccounts.includes(option.account)
              ? selectedAccounts.filter((account) => account !== option.account)
              : [...selectedAccounts, option.account];
            return (
              <button
                key={option.account}
                type="button"
                className={`max-w-full rounded-md border px-3 py-2 text-left text-sm font-semibold sm:max-w-[22rem] ${active ? "border-brand bg-brand text-white dark:text-slate-950" : "border-border bg-panel text-muted"}`}
                title={`${option.first_seen || "unknown"} to ${option.last_seen || "unknown"}`}
                onClick={() => applyAccounts(nextAccounts)}
              >
                <span className="break-anywhere">{option.account}</span>
              </button>
            );
          })}
        </div>
      ) : (
        <div className="text-sm text-muted">No account snapshots yet. The service will record one on the next monitor tick.</div>
      )}
    </div>
  ) : null;
  const overviewControls = (
    <UsageWindowControls
      applyRange={applyRange}
      draftRange={draftRange}
      rangeError={rangeError}
      setDraftRange={setDraftRange}
      timezone={timezone}
    />
  );
  const chartControlsNode = (
    <div className="flex flex-wrap gap-2">
      <div className="inline-flex rounded-md border border-border bg-panel p-1">
        {groupModes.map((mode) => (
          <button
            key={mode.id}
            type="button"
            className={`rounded px-3 py-1.5 text-sm font-semibold ${groupMode === mode.id ? "bg-brand text-white dark:text-slate-950" : "text-muted"}`}
            onClick={() => applyGroupMode(mode.id)}
          >
            {mode.label}
          </button>
        ))}
      </div>
      <div className="inline-flex rounded-md border border-border bg-panel p-1">
        {chartModes.map((mode) => (
          <button
            key={mode.id}
            type="button"
            className={`inline-flex items-center gap-2 rounded px-3 py-1.5 text-sm font-semibold ${chartMode === mode.id ? "bg-brand text-white dark:text-slate-950" : "text-muted"}`}
            onClick={() => applyChartMode(mode.id)}
          >
            {mode.icon}
            {mode.label}
          </button>
        ))}
      </div>
    </div>
  );
  const seriesControlsNode = (
    <div className="flex flex-wrap gap-2">
      {[
        { key: "credits" as const, label: "Credits" },
        { key: "uncached" as const, label: "Uncached" },
        { key: "cached" as const, label: "Cached" },
        { key: "output" as const, label: "Output" },
      ].map((series) => (
        <button
          key={series.key}
          type="button"
          className={`rounded-md border px-3 py-1.5 text-sm font-semibold ${visibleSeries[series.key] ? "border-brand bg-brand text-white dark:text-slate-950" : "border-border bg-panel text-muted"}`}
          onClick={() => toggleSeries(series.key)}
        >
          {series.label}
        </button>
      ))}
      {daysFetching ? <Spinner label="Updating chart" /> : null}
    </div>
  );
  const overviewChart = (
    <div className={chartBusyClass} aria-busy={chartsBusy}>
      {daysLoading ? (
        <LoaderBlock label="Loading daily usage" />
      ) : (
        <DashboardChart
          mode={chartMode}
          rows={groupedRows}
          safeDailySpend={groupMode === "day" ? safeDailySpend : null}
          visibleSeries={visibleSeries}
        />
      )}
    </div>
  );

  function toggleSeries(series: keyof typeof visibleSeries) {
    setVisibleSeries((current) => ({ ...current, [series]: !current[series] }));
  }

  return (
    <>
      <DataWarning warnings={dataWarnings} />

      <MonitorAccountBar
        focusedAccount={focusedAccount}
        activeAccount={activeAccount}
        options={monitorOptions}
        onChange={setMonitorFocusOverride}
      />

      <DashboardOverview
        accountDetail={accountDetail}
        accountFilter={accountFilterNode}
        cacheDetail={days?.cache?.hit ? "Range cache hit" : daysFetching ? "Refreshing range data" : cacheBackendLabel(snapshot?.cache)}
        chart={overviewChart}
        chartControls={chartControlsNode}
        controls={overviewControls}
        driverSource={{
          accountRows: summary?.by_account || [],
          modelRows: summary?.by_model || [],
          effortRows: summary?.by_effort || [],
          projectRows: sessionsFresh ? sessions?.by_project || [] : [],
          projectRowsFresh: sessionsFresh,
        }}
        generatedAtDetail={`Updated ${formatDateTime(snapshot?.generated_at)}`}
        rangeLabel={overviewRangeLabel}
        seriesControls={seriesControlsNode}
        totals={overviewTotals}
        visibleDays={groupedRows.length || days?.days.length || 0}
      />

      <DashboardLimitsPanel focusedStatus={focusedStatus} statuses={accountLimitStatuses} />

      <ActionCenter
        accounts={accounts}
        advisories={advisories}
        alerts={alerts}
        focusedAccount={focusedAccount}
        focusedStatus={focusedStatus}
        onOpenSettings={onOpenSettings}
        sessions={sessions}
        sessionsFresh={sessionsFresh}
        sessionsFetching={sessionsFetching}
        signalThresholds={signalThresholds}
        snapshot={snapshot}
        updateStatus={updateStatus}
        maxItems={3}
      />

      <div className="grid gap-4 xl:grid-cols-[1.2fr_.8fr]">
        <Panel title="Credit Trend" meta={summaryFetching ? <Spinner label="Updating" /> : groupModes.find((mode) => mode.id === groupMode)?.label}>
          <div className={chartBusyClass} aria-busy={chartsBusy}>
            {daysLoading ? <LoaderBlock label="Loading credit trend" /> : <CreditAreaChart rows={groupedRows} />}
          </div>
        </Panel>
        <Panel title="Service">
          <dl className="grid grid-cols-[max-content_1fr] gap-x-4 gap-y-2 text-sm">
            <dt className="text-muted">Timezone</dt><dd>{snapshot?.timezone || "Loading"}</dd>
            <dt className="text-muted">Pricing</dt><dd>Codex credits</dd>
            <dt className="text-muted">USD/ZAR</dt><dd>{exchangeRateLabel}</dd>
            <dt className="text-muted">Cache</dt><dd>{cacheBackendLabel(snapshot?.cache)}</dd>
          </dl>
        </Panel>
      </div>

      <div className={`grid gap-4 ${focusedMode ? "xl:grid-cols-2" : "xl:grid-cols-3"}`}>
        {!focusedMode && !singleAccount ? <Panel title="By Account" meta={summaryFetching ? <Spinner label="Updating" /> : null}>
          {summaryLoading ? <LoaderBlock label="Loading account breakdown" /> : <BreakdownTable rows={summary?.by_account || []} labelKey="account" totalCredits={summary?.totals.total_credits || 0} />}
        </Panel> : null}
        <Panel title="By Model" meta={summaryFetching ? <Spinner label="Updating" /> : null}>
          {summaryLoading ? <LoaderBlock label="Loading model breakdown" /> : <BreakdownTable rows={summary?.by_model || []} labelKey="model" totalCredits={summary?.totals.total_credits || 0} />}
        </Panel>
        <Panel title="By Effort" meta={summaryFetching ? <Spinner label="Updating" /> : null}>
          {summaryLoading ? <LoaderBlock label="Loading effort breakdown" /> : <BreakdownTable rows={summary?.by_effort || []} labelKey="effort" totalCredits={summary?.totals.total_credits || 0} />}
        </Panel>
      </div>

      {snapshotLoading || snapshot?.budgets?.length ? (
        <div className="grid gap-4">
          <Panel title="Budgets" meta={<WalletCards className="h-4 w-4 text-brand" />}>
            {snapshotLoading ? <LoaderBlock label="Loading budgets" /> : <BudgetList budgets={snapshot?.budgets || []} />}
          </Panel>
        </div>
      ) : null}

      <Panel title="Recent Alerts" meta={alertsFetching ? <Spinner label="Checking" /> : <Bell className="h-4 w-4 text-brand" />}>
        {alertsLoading ? (
          <LoaderBlock label="Loading alerts" />
        ) : alerts?.length ? (
          <div className="divide-y divide-border">
            {alerts.map((alert) => (
              <div key={alert.id} className="flex flex-wrap items-center justify-between gap-3 py-3 text-sm">
                <div>
                  <div className="font-semibold">
                    {alert.type === "account_burn_alert"
                      ? `${alert.account} · ${alert.message || "Burn alert"}`
                      : alert.account || alert.period}
                  </div>
                  <div className="text-muted">{formatDateTime(alert.created_at)}</div>
                </div>
                <div className="font-semibold text-danger">
                  {alert.type === "account_burn_alert"
                    ? alert.value || alert.projected_exhaustion_label || `${alert.severity || "warning"}`
                    : alert.account
                    ? `${formatLimitValue(alert.current_value || 0, alert.metric)} / ${formatLimitValue(alert.cap_value || 0, alert.metric)}`
                    : `${compactCredits(alert.current_credits || 0)} / ${compactCredits(alert.budget_credits || 0)}`}
                </div>
              </div>
            ))}
          </div>
        ) : (
          <div className="rounded-md border border-brand/25 bg-brand/5 p-3 text-sm text-muted">No alerts in this window.</div>
        )}
      </Panel>

    </>
  );
}
