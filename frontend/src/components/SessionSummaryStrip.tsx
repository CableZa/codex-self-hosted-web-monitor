import { Activity, Clock3, Database, Eye, WalletCards } from "lucide-react";
import type { SessionHistoryReport } from "../lib/apiTypes";
import { compactCredits, fmtCompactNum } from "../lib/format";

function SummaryCell({ icon, label, value, detail }: { icon: React.ReactNode; label: string; value: string; detail?: string }) {
  return (
    <div className="min-w-0 border-b border-border/70 p-3 sm:border-b-0 sm:border-r last:sm:border-r-0">
      <div className="flex items-center gap-2 text-xs font-semibold uppercase text-muted">
        {icon}
        <span>{label}</span>
      </div>
      <div className="mt-1 break-words text-xl font-bold text-ink">{value}</div>
      {detail ? <div className="mt-0.5 truncate text-xs text-muted">{detail}</div> : null}
    </div>
  );
}

export function SessionSummaryStrip({
  scopeLabel,
  sessionRowsCount,
  sessions,
  sessionsFetching,
  visibleCount,
}: {
  scopeLabel: string;
  sessionRowsCount: number;
  sessions?: SessionHistoryReport;
  sessionsFetching: boolean;
  visibleCount: number;
}) {
  const totals = sessions?.totals;
  return (
    <section className="overflow-hidden rounded-sm border border-border bg-panel/95">
      <div className="flex flex-wrap items-center justify-between gap-2 border-b border-border/70 bg-canvas/55 px-3 py-2">
        <div className="min-w-0">
          <div className="text-xs font-semibold uppercase text-brand">Session Scope</div>
          <div className="truncate text-sm font-semibold text-ink">{scopeLabel}</div>
        </div>
        <div className="rounded-sm border border-border bg-panel px-2 py-1 text-xs font-semibold text-muted">
          {sessionsFetching ? "Refreshing" : "Current"}
        </div>
      </div>
      <div className="grid sm:grid-cols-3 xl:grid-cols-6">
        <SummaryCell
          icon={<Activity className="h-4 w-4 text-brand" />}
          label="Sessions"
          value={fmtCompactNum.format(sessionRowsCount)}
          detail={`${fmtCompactNum.format(visibleCount)} visible`}
        />
        <SummaryCell
          icon={<Eye className="h-4 w-4 text-brand" />}
          label="Visible"
          value={fmtCompactNum.format(visibleCount)}
          detail={visibleCount === sessionRowsCount ? "No session filters" : "Filtered result"}
        />
        <SummaryCell
          icon={<WalletCards className="h-4 w-4 text-brand" />}
          label="Credits"
          value={compactCredits(totals?.total_credits || 0)}
          detail="Selected range"
        />
        <SummaryCell
          icon={<Database className="h-4 w-4 text-brand" />}
          label="Uncached"
          value={fmtCompactNum.format(totals?.uncached_input_tokens || 0)}
          detail="Input tokens"
        />
        <SummaryCell
          icon={<Database className="h-4 w-4 text-cached-input" />}
          label="Cached"
          value={fmtCompactNum.format(totals?.cached_input_tokens || 0)}
          detail="Input tokens"
        />
        <SummaryCell
          icon={<Clock3 className="h-4 w-4 text-output" />}
          label="Output"
          value={fmtCompactNum.format(totals?.output_tokens || 0)}
          detail="Tokens"
        />
      </div>
    </section>
  );
}
