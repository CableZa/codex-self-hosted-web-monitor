import { useMemo, useState, type ReactNode } from "react";
import { Activity, CircleDollarSign, Database, Gauge, Layers3, LineChart, PieChart, Server } from "lucide-react";
import type { BreakdownRow, SessionProjectRow, UsageTotals } from "../lib/apiTypes";
import { compactCredits, fmtCompactNum, pct } from "../lib/format";

type DriverSegment = "account" | "model" | "effort" | "project";

type CostDriverRow = {
  id: string;
  label: string;
  total_credits: number;
  total_tokens: number;
};

type DriverSource = {
  accountRows: BreakdownRow[];
  modelRows: BreakdownRow[];
  effortRows: BreakdownRow[];
  projectRows: SessionProjectRow[];
  projectRowsFresh: boolean;
};

const driverLabels: Record<DriverSegment, string> = {
  account: "Account",
  model: "Model",
  effort: "Effort",
  project: "Project",
};

function numberValue(value: unknown) {
  return typeof value === "number" && Number.isFinite(value) ? value : Number(value || 0);
}

function driverRows(segment: DriverSegment, source: DriverSource): CostDriverRow[] {
  const rows = segment === "account"
    ? source.accountRows.map((row) => ({ id: row.account || "unknown", label: row.account || "unknown", total_credits: row.total_credits || 0, total_tokens: row.total_tokens || 0 }))
    : segment === "model"
      ? source.modelRows.map((row) => ({ id: row.model || "unknown", label: row.model || "unknown", total_credits: row.total_credits || 0, total_tokens: row.total_tokens || 0 }))
      : segment === "effort"
        ? source.effortRows.map((row) => ({ id: row.effort || "unknown", label: row.effort || "unknown", total_credits: row.total_credits || 0, total_tokens: row.total_tokens || 0 }))
        : source.projectRows.map((row) => ({ id: `${row.project}-${row.project_path || ""}`, label: row.project || "Unknown project", total_credits: row.total_credits || 0, total_tokens: row.total_tokens || 0 }));
  return rows.sort((left, right) => right.total_credits - left.total_credits).slice(0, 3);
}

function availableSegments(source: DriverSource): DriverSegment[] {
  const segments: DriverSegment[] = [];
  if (source.accountRows.length > 1) segments.push("account");
  if (source.modelRows.length) segments.push("model");
  if (source.effortRows.length) segments.push("effort");
  if (source.projectRowsFresh && source.projectRows.length) segments.push("project");
  return segments.length ? segments : ["model"];
}

function defaultSegment(source: DriverSource): DriverSegment {
  if (source.accountRows.length > 1) return "account";
  if (source.modelRows.length) return "model";
  if (source.effortRows.length) return "effort";
  if (source.projectRowsFresh && source.projectRows.length) return "project";
  return "model";
}

function OverviewStat({ tone = "brand", label, value, detail, icon }: { tone?: "brand" | "live" | "accent" | "muted"; label: string; value: string; detail: string; icon: ReactNode }) {
  const toneClass = tone === "live" ? "text-live" : tone === "accent" ? "text-accent" : tone === "muted" ? "text-muted" : "text-brand";
  return (
    <div className="min-w-0 border-t border-border/70 px-3 py-3 first:border-l-0 sm:border-l sm:border-t-0">
      <div className={`mb-2 inline-flex items-center gap-2 text-xs font-bold uppercase tracking-normal ${toneClass}`}>
        {icon}
        <span>{label}</span>
      </div>
      <div className="break-words text-xl font-bold tracking-normal text-ink">{value}</div>
      <div className="mt-1 text-xs text-muted">{detail}</div>
    </div>
  );
}

function CostDrivers({ source, totalCredits }: { source: DriverSource; totalCredits: number }) {
  const segments = useMemo(() => availableSegments(source), [source]);
  const [segment, setSegment] = useState<DriverSegment>(() => defaultSegment(source));
  const activeSegment = segments.includes(segment) ? segment : segments[0];
  const rows = driverRows(activeSegment, source);

  return (
    <div className="rounded-md border border-border bg-panel/90 p-3 shadow-sm">
      <div className="mb-3 flex flex-wrap items-center justify-between gap-2">
        <div className="inline-flex items-center gap-2 text-sm font-bold text-ink">
          <PieChart className="h-4 w-4 text-brand" />
          Cost drivers
        </div>
        <div className="inline-flex rounded-md border border-border bg-canvas p-1">
          {segments.map((item) => (
            <button
              key={item}
              type="button"
              className={`rounded px-2.5 py-1 text-xs font-bold ${activeSegment === item ? "bg-panel text-ink shadow-sm" : "text-muted"}`}
              onClick={() => setSegment(item)}
            >
              {driverLabels[item]}
            </button>
          ))}
        </div>
      </div>
      {rows.length ? (
        <div className="grid gap-3">
          {rows.map((row, index) => {
            const share = totalCredits > 0 ? Math.min(100, Math.round((row.total_credits / totalCredits) * 100)) : 0;
            return (
              <div key={row.id} className="grid gap-1.5">
                <div className="flex items-start justify-between gap-3 text-sm">
                  <div className="flex min-w-0 items-center gap-2">
                    <span className="w-4 shrink-0 text-xs font-bold text-muted">{index + 1}</span>
                    <span className="break-anywhere font-semibold text-ink">{row.label}</span>
                  </div>
                  <div className="shrink-0 text-right">
                    <div className="font-bold text-ink">{compactCredits(row.total_credits)}</div>
                    <div className="text-xs text-muted">{fmtCompactNum.format(row.total_tokens)} tokens</div>
                  </div>
                </div>
                <div className="h-2 overflow-hidden rounded-full bg-border/50">
                  <div className="h-full rounded-full bg-brand" style={{ width: `${share}%` }} />
                </div>
                <div className="text-right text-xs font-semibold text-muted">{share}%</div>
              </div>
            );
          })}
        </div>
      ) : (
        <div className="rounded-md border border-border bg-canvas/70 p-3 text-sm text-muted">No cost-driver data for this range yet.</div>
      )}
    </div>
  );
}

export function DashboardOverview({
  accountDetail,
  accountFilter,
  cacheDetail,
  chart,
  chartControls,
  controls,
  driverSource,
  generatedAtDetail,
  rangeLabel,
  seriesControls,
  totals,
  visibleDays,
}: {
  accountDetail: string;
  accountFilter?: ReactNode;
  cacheDetail: string;
  chart: ReactNode;
  chartControls: ReactNode;
  controls: ReactNode;
  driverSource: DriverSource;
  generatedAtDetail: string;
  rangeLabel: string;
  seriesControls: ReactNode;
  totals: Partial<UsageTotals>;
  visibleDays: number;
}) {
  const totalCredits = numberValue(totals.total_credits);
  const totalTokens = numberValue(totals.total_tokens);
  const cachedTokens = numberValue(totals.cached_input_tokens);
  const uncachedTokens = numberValue(totals.uncached_input_tokens);
  const inputTokens = cachedTokens + uncachedTokens || numberValue(totals.input_tokens);
  const cacheRatio = inputTokens > 0 ? cachedTokens / inputTokens : 0;
  const avgCredits = visibleDays > 0 ? totalCredits / visibleDays : 0;
  const blendedCredits = totalTokens > 0 ? (totalCredits / totalTokens) * 1_000_000 : 0;

  return (
    <section className="overflow-hidden rounded-lg border border-border bg-panel shadow-sm">
      <div className="grid gap-5 p-4 sm:p-5 xl:grid-cols-[minmax(20rem,0.72fr)_minmax(0,1.28fr)]">
        <div className="min-w-0">
          <div className="text-xs font-bold uppercase tracking-normal text-brand">Overview</div>
          <h2 className="mt-2 break-words text-3xl font-bold tracking-normal text-ink sm:text-4xl">Codex Credit Usage</h2>
          <div className="mt-2 text-sm text-muted">{rangeLabel}</div>
          <div className="mt-5">
            <div className="text-xs font-bold uppercase tracking-normal text-muted">Selected range credits</div>
            <div className="mt-1 flex flex-wrap items-end gap-x-3 gap-y-1">
              <div className="break-words text-4xl font-black tracking-normal text-ink sm:text-5xl">{compactCredits(totalCredits)}</div>
              <div className="pb-1 text-sm font-bold text-live">{fmtCompactNum.format(totalTokens)} tokens</div>
            </div>
          </div>
          <div className="mt-5 grid gap-2 border-y border-border/70 py-4 text-sm text-muted">
            <div className="inline-flex min-w-0 items-center gap-2">
              <Layers3 className="h-4 w-4 shrink-0 text-muted" />
              <span className="break-anywhere">{accountDetail}</span>
            </div>
            <div className="inline-flex min-w-0 items-center gap-2">
              <Database className="h-4 w-4 shrink-0 text-muted" />
              <span>{cacheDetail}</span>
            </div>
            <div className="inline-flex min-w-0 items-center gap-2">
              <Server className="h-4 w-4 shrink-0 text-muted" />
              <span>{generatedAtDetail}</span>
            </div>
          </div>
          <div className="mt-4 grid gap-3">
            {controls}
            {accountFilter}
            <CostDrivers source={driverSource} totalCredits={totalCredits} />
          </div>
        </div>

        <div className="min-w-0 rounded-lg border border-border bg-canvas/55 shadow-sm">
          <div className="flex flex-wrap items-center justify-between gap-3 border-b border-border/70 px-3 py-3">
            {chartControls}
            {seriesControls}
          </div>
          <div className="px-2 py-3 sm:px-3">{chart}</div>
          <div className="grid border-t border-border/70 bg-panel/75 sm:grid-cols-4">
            <OverviewStat label="Tokens" value={fmtCompactNum.format(totalTokens)} detail="Selected range" icon={<Activity className="h-3.5 w-3.5" />} />
            <OverviewStat tone="accent" label="Avg / day" value={compactCredits(avgCredits)} detail={`${Math.max(visibleDays, 0)} day window`} icon={<LineChart className="h-3.5 w-3.5" />} />
            <OverviewStat tone="live" label="Cache hit" value={pct(cacheRatio)} detail={`${fmtCompactNum.format(cachedTokens)} cached input`} icon={<Gauge className="h-3.5 w-3.5" />} />
            <OverviewStat tone="muted" label="Cost / 1M" value={compactCredits(blendedCredits)} detail="Blended credit rate" icon={<CircleDollarSign className="h-3.5 w-3.5" />} />
          </div>
        </div>
      </div>
    </section>
  );
}
