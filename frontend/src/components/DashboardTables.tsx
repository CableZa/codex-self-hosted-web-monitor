import type { BreakdownRow, Budget } from "../lib/apiTypes";
import type { BreakdownLabelKey } from "../lib/usage";
import { compactCredits, fmtCompactNum, pct } from "../lib/format";

export function BreakdownTable({ rows, labelKey, totalCredits }: { rows: BreakdownRow[]; labelKey: BreakdownLabelKey; totalCredits: number }) {
  if (!rows.length) return <div className="text-sm text-muted">No usage found for this range.</div>;
  return (
    <div className="space-y-2">
      {rows.map((row) => {
        const share = totalCredits > 0 ? Math.min(100, Math.round((Number(row.total_credits || 0) / totalCredits) * 100)) : 0;
        return (
          <div key={`${labelKey}-${row[labelKey]}`} className="rounded-lg border border-border bg-canvas/50 p-3">
            <div className="flex items-start justify-between gap-4">
              <div className="min-w-0">
                <div className="truncate font-semibold text-ink">{row[labelKey] || "unknown"}</div>
                <div className="mt-1 text-xs text-muted">{fmtCompactNum.format(row.events || 0)} events</div>
              </div>
              <div className="text-right">
                <div className="font-bold text-brand">{compactCredits(row.total_credits || 0)}</div>
                <div className="text-xs text-muted">{fmtCompactNum.format(row.total_tokens || 0)} tokens</div>
              </div>
            </div>
            <div className="mt-3 h-2 overflow-hidden rounded-full bg-border/60">
              <div className="h-full rounded-full bg-brand" style={{ width: `${share}%` }} />
            </div>
          </div>
        );
      })}
    </div>
  );
}

export function BudgetList({ budgets }: { budgets: Budget[] }) {
  return (
    <div className="space-y-4">
      {budgets.map((budget) => {
        const label = budget.period === "today" ? "Daily" : budget.period[0].toUpperCase() + budget.period.slice(1);
        const width = Math.min(100, Math.round(budget.ratio * 100));
        return (
          <div key={budget.period}>
            <div className="flex justify-between gap-3 text-sm">
              <span className="font-semibold">{label}</span>
              <span className="text-muted">{compactCredits(budget.current_credits)} / {compactCredits(budget.budget_credits)}</span>
            </div>
            <div className="mt-2 h-3 overflow-hidden rounded-full bg-border/60">
              <div className={`h-full rounded-full ${budget.exceeded ? "bg-danger" : "bg-brand"}`} style={{ width: `${width}%` }} />
            </div>
            <div className="mt-1 text-xs text-muted">{pct(budget.ratio)} used</div>
          </div>
        );
      })}
    </div>
  );
}
