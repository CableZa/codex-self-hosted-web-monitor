import { Gauge, ShieldAlert, ShieldCheck } from "lucide-react";
import type { AccountLimitStatus } from "../lib/apiTypes";
import { formatDateTime, formatLimitValue, pct } from "../lib/format";

function severityLabel(status: AccountLimitStatus) {
  if (status.exceeded) return "Exceeded";
  if (status.burn_severity === "critical") return "Critical";
  if (status.burn_severity === "warning") return "Near limit";
  if (status.burn_severity === "info") return "Watch";
  return "Healthy";
}

function severityClass(status: AccountLimitStatus) {
  if (status.exceeded || status.burn_severity === "critical") return "border-danger/45 bg-danger/10 text-danger";
  if (status.burn_severity === "warning") return "border-accent/45 bg-accent/10 text-accent";
  if (status.burn_severity === "info") return "border-brand/40 bg-brand/10 text-brand";
  return "border-live/35 bg-live/10 text-live";
}

function riskRank(status: AccountLimitStatus) {
  if (!status.enabled) return -1;
  const severity = status.exceeded ? 5 : status.burn_severity === "critical" ? 4 : status.burn_severity === "warning" ? 3 : status.burn_severity === "info" ? 2 : 1;
  return severity * 1000 + status.ratio;
}

function LimitTile({ status, label }: { status?: AccountLimitStatus; label: string }) {
  if (!status) {
    return (
      <div className="rounded-lg border border-dashed border-border bg-canvas/55 p-4">
        <div className="inline-flex items-center gap-2 text-sm font-bold text-muted">
          <ShieldAlert className="h-4 w-4" />
          {label}
        </div>
        <div className="mt-3 text-sm text-muted">No weekly credit limit is configured for this slot.</div>
      </div>
    );
  }

  const width = Math.min(100, Math.round(status.ratio * 100));
  const remaining = status.exceeded ? "0 remaining" : `${formatLimitValue(status.remaining_value, status.metric)} remaining`;
  return (
    <div className="rounded-lg border border-border bg-canvas/55 p-4">
      <div className="mb-4 flex flex-wrap items-start justify-between gap-3">
        <div className="min-w-0">
          <div className="text-xs font-bold uppercase tracking-normal text-muted">{label}</div>
          <div className="mt-1 break-anywhere text-base font-bold text-ink">{status.account}</div>
          <div className="mt-1 text-xs text-muted">Resets {formatDateTime(status.reset_at)}</div>
        </div>
        <span className={`inline-flex items-center gap-1.5 rounded-full border px-2.5 py-1 text-xs font-bold ${severityClass(status)}`}>
          {status.burn_severity === "ok" ? <ShieldCheck className="h-3.5 w-3.5" /> : <Gauge className="h-3.5 w-3.5" />}
          {severityLabel(status)}
        </span>
      </div>
      <div className="grid gap-4 sm:grid-cols-[5rem_1fr] sm:items-center">
        <div className="grid h-16 w-16 place-items-center rounded-full border-4 border-brand/80 bg-panel text-center">
          <div>
            <div className="text-lg font-black text-ink">{pct(Math.max(0, 1 - status.ratio))}</div>
            <div className="text-[0.62rem] font-bold uppercase text-muted">left</div>
          </div>
        </div>
        <div className="min-w-0">
          <div className="text-2xl font-bold text-ink">{pct(status.ratio)} <span className="text-sm font-semibold text-muted">used</span></div>
          <div className="mt-1 break-words text-sm font-semibold text-brand">{status.projected_exhaustion_label}</div>
          <div className="mt-3 h-2 overflow-hidden rounded-full bg-border/60">
            <div className={`h-full rounded-full ${status.exceeded ? "bg-danger" : status.burn_severity === "warning" ? "bg-accent" : "bg-brand"}`} style={{ width: `${width}%` }} />
          </div>
          <div className="mt-2 grid grid-cols-2 gap-2 border-t border-border/70 pt-2 text-xs">
            <div>
              <div className="font-bold uppercase text-muted">Consumed</div>
              <div className="font-bold text-ink">{formatLimitValue(status.current_value, status.metric)}</div>
            </div>
            <div>
              <div className="font-bold uppercase text-muted">Window</div>
              <div className="font-bold text-ink">{remaining}</div>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}

export function DashboardLimitsPanel({
  focusedStatus,
  statuses,
}: {
  focusedStatus?: AccountLimitStatus;
  statuses: AccountLimitStatus[];
}) {
  const secondaryStatus = [...statuses]
    .filter((status) => status.enabled && status.account !== focusedStatus?.account)
    .sort((left, right) => riskRank(right) - riskRank(left))[0];

  return (
    <section className="rounded-lg border border-border bg-panel shadow-sm">
      <div className="flex flex-wrap items-center justify-between gap-3 border-b border-border px-4 py-3 sm:px-5">
        <div className="min-w-0">
          <div className="inline-flex items-center gap-2 text-xl font-bold text-ink">
            <Gauge className="h-5 w-5 text-brand" />
            Codex Limits
          </div>
          <div className="mt-1 text-sm text-muted">Live weekly credit limits from local Codex activity.</div>
        </div>
        {focusedStatus ? <div className="text-xs font-semibold text-muted">Updated {formatDateTime(focusedStatus.window_end_at)}</div> : null}
      </div>
      <div className="grid gap-3 p-4 sm:p-5 xl:grid-cols-2">
        <LimitTile label="Focused account" status={focusedStatus} />
        <LimitTile label="Highest risk" status={secondaryStatus} />
      </div>
    </section>
  );
}
