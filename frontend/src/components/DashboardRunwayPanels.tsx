import { Flame, Gauge, ShieldCheck } from "lucide-react";
import type { AccountLimitStatus } from "../lib/apiTypes";
import { shouldShowMonitorAccountSelector } from "../lib/accountMonitoring";
import type { SignalSeverity } from "../lib/dashboardSignals";
import { formatDateTime, formatLimitValue } from "../lib/format";
import { Panel } from "./Panel";

const severityClasses: Record<SignalSeverity, string> = {
  critical: "border-danger/45 bg-danger/10 text-danger",
  warning: "border-accent/45 bg-accent/10 text-accent",
  info: "border-brand/35 bg-brand/10 text-brand",
  ok: "border-brand/30 bg-brand/5 text-brand",
};

export type BurnAdvisory = AccountLimitStatus["burn_advisories"][number];

function RunwayMetric({ label, value }: { label: string; value: string }) {
  return (
    <div className="min-w-0 rounded-md border border-border bg-canvas/60 p-3">
      <div className="text-[0.68rem] font-bold uppercase tracking-normal text-muted">{label}</div>
      <div className="mt-1 break-words text-lg font-bold text-ink">{value}</div>
    </div>
  );
}

export function MonitorAccountBar({
  focusedAccount,
  activeAccount,
  options,
  onChange,
}: {
  focusedAccount: string;
  activeAccount: string;
  options: string[];
  onChange: (account: string) => void;
}) {
  if (!shouldShowMonitorAccountSelector(options)) return null;
  return (
    <div className="rounded-lg border border-border bg-panel/80 p-3">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div className="min-w-0">
          <div className="inline-flex items-center gap-2 text-sm font-semibold text-ink">
            <Gauge className="h-4 w-4 text-brand" />
            Monitoring account
          </div>
          <p className="mt-1 text-sm text-muted">Runway, burn alerts, and focused limit warnings follow this account.</p>
        </div>
        <div className="inline-flex items-center gap-2 rounded-full border border-border bg-canvas/70 px-2 py-1 text-xs font-semibold text-muted">
          <span>Inspect</span>
          <select
            className="min-w-[13rem] bg-transparent text-ink outline-none"
            value={focusedAccount}
            onChange={(event) => onChange(event.target.value)}
          >
            {options.map((account) => (
              <option key={account} value={account}>
                {account === activeAccount ? `${account} (active)` : account}
              </option>
            ))}
          </select>
        </div>
      </div>
    </div>
  );
}

export function WeeklyRunwayPanel({
  focusedAccount,
  focusedStatus,
  onOpenSettings,
}: {
  focusedAccount: string;
  focusedStatus?: AccountLimitStatus;
  onOpenSettings: () => void;
}) {
  if (!focusedAccount) {
    return (
      <Panel title="Weekly Credit Runway" meta={<Gauge className="h-4 w-4 text-brand" />}>
        <div className="rounded-md border border-border bg-canvas/60 p-3 text-sm text-muted">
          A confirmed active account has not been observed yet.
        </div>
      </Panel>
    );
  }

  if (!focusedStatus) {
    return (
      <Panel title="Weekly Credit Runway" meta={<Gauge className="h-4 w-4 text-brand" />} className="bg-panel/95">
        <div className="rounded-md border border-accent/35 bg-accent/10 p-3 text-sm text-accent">
          {focusedAccount} is active, but it does not have a weekly credit limit yet.
        </div>
        <button
          type="button"
          className="mt-3 inline-flex items-center gap-2 rounded-md border border-border bg-panel/70 px-3 py-2 text-sm font-semibold text-ink"
          onClick={onOpenSettings}
        >
          Open Settings
        </button>
      </Panel>
    );
  }

  const paceLabel = focusedStatus.spend_rate_vs_target > 0 ? `${focusedStatus.spend_rate_vs_target.toFixed(1)}x target` : "No spend yet";
  return (
    <Panel
      title="Weekly Credit Runway"
      meta={<Gauge className="h-4 w-4 text-brand" />}
      className="bg-panel/95"
    >
      <div className="mb-3 flex flex-wrap items-center justify-between gap-2">
        <div>
          <div className="text-sm font-semibold text-ink">{focusedAccount}</div>
          <div className="text-xs text-muted">Resets {formatDateTime(focusedStatus.reset_at)}</div>
        </div>
        <span className={`inline-flex items-center gap-1.5 rounded-full border px-2.5 py-1 text-xs font-semibold ${severityClasses[focusedStatus.burn_severity]}`}>
          <Gauge className="h-3.5 w-3.5" />
          {paceLabel}
        </span>
      </div>
      <div className="grid gap-3 md:grid-cols-4">
        <RunwayMetric label="Credits left this week" value={formatLimitValue(focusedStatus.remaining_value, focusedStatus.metric)} />
        <RunwayMetric label="Safe daily spend" value={formatLimitValue(focusedStatus.safe_daily_spend, focusedStatus.metric)} />
        <RunwayMetric label="Projected exhaustion" value={focusedStatus.projected_exhaustion_label} />
        <RunwayMetric label="Spend rate vs target" value={paceLabel} />
      </div>
      <div className="mt-3 h-2 overflow-hidden rounded-full bg-border/60">
        <div
          className={`h-full rounded-full ${focusedStatus.burn_severity === "critical" ? "bg-danger" : focusedStatus.burn_severity === "warning" ? "bg-accent" : "bg-brand"}`}
          style={{ width: `${Math.min(100, Math.round(focusedStatus.ratio * 100))}%` }}
        />
      </div>
      <div className="mt-2 flex flex-wrap items-center justify-between gap-2 text-xs text-muted">
        <span>{formatLimitValue(focusedStatus.current_value, focusedStatus.metric)} used of {formatLimitValue(focusedStatus.cap_value, focusedStatus.metric)}</span>
        <span>{focusedStatus.remaining_days} day{focusedStatus.remaining_days === 1 ? "" : "s"} remaining</span>
      </div>
    </Panel>
  );
}

export function BurnAdvisoryPanel({
  activeAccount,
  focusedAccount,
  focusedStatus,
  advisories,
}: {
  activeAccount: string;
  focusedAccount: string;
  focusedStatus?: AccountLimitStatus;
  advisories: BurnAdvisory[];
}) {
  if (!focusedAccount) {
    return (
      <Panel title="Burn Alerts" meta={<ShieldCheck className="h-4 w-4 text-muted" />}>
        <div className="rounded-md border border-border bg-canvas/60 p-3 text-sm text-muted">
          Burn alerts appear after the monitor can identify an active account.
        </div>
      </Panel>
    );
  }

  if (!focusedStatus) {
    return (
      <Panel title="Burn Alerts" meta={<ShieldCheck className="h-4 w-4 text-muted" />}>
        <div className="rounded-md border border-border bg-canvas/60 p-3 text-sm text-muted">
          {focusedAccount === activeAccount ? "The active account" : focusedAccount} needs a weekly credit limit before predictive burn alerts can evaluate spend pace.
        </div>
      </Panel>
    );
  }

  if (!advisories.length) {
    return (
      <Panel title="Burn Alerts" meta={<ShieldCheck className="h-4 w-4 text-brand" />}>
        <div className="rounded-md border border-brand/25 bg-brand/5 p-3 text-sm text-muted">
          {focusedAccount} is currently tracking inside the decision-support guardrails.
        </div>
      </Panel>
    );
  }

  return (
    <Panel title="Burn Alerts" meta={<Flame className="h-4 w-4 text-accent" />}>
      <div className="grid gap-2">
        {advisories.map((advisory) => (
          <div key={advisory.id} className={`rounded-md border p-3 ${severityClasses[advisory.severity]}`}>
            <div className="flex flex-wrap items-start justify-between gap-3">
              <div className="min-w-0">
                <div className="font-semibold text-ink">{advisory.message}</div>
                <div className="mt-1 text-xs text-muted">{advisory.label}</div>
              </div>
              <div className="text-right text-sm font-bold">{advisory.value}</div>
            </div>
          </div>
        ))}
      </div>
    </Panel>
  );
}
