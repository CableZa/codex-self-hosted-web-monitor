import type { BreakdownRow, DaysReport, SnapshotCacheStatus, UsageDay, UsageReport, UsageTotals } from "./apiTypes";
import type { GroupMode } from "./dashboardState";

export const focusedAccountDomains = ["@example.com", "@example.org"];
export const fallbackFocusedAccounts = ["work@example.com"];

export function rangeTotals(days: UsageDay[]) {
  return days.reduce(
    (totals, row) => {
      totals.input_tokens += Number(row.input_tokens || 0);
      totals.cached_input_tokens = Number(totals.cached_input_tokens || 0) + Number(row.cached_input_tokens || 0);
      totals.uncached_input_tokens = Number(totals.uncached_input_tokens || 0) + Number(row.uncached_input_tokens || 0);
      totals.output_tokens += Number(row.output_tokens || 0);
      totals.total_tokens += Number(row.total_tokens || 0);
      totals.total_usd += Number(row.total_usd || 0);
      totals.total_zar += Number(row.total_zar || 0);
      totals.input_credits += Number(row.input_credits || 0);
      totals.cached_input_credits = Number(totals.cached_input_credits || 0) + Number(row.cached_input_credits || 0);
      totals.output_credits += Number(row.output_credits || 0);
      totals.total_credits += Number(row.total_credits || 0);
      return totals;
    },
    {
      input_tokens: 0,
      cached_input_tokens: 0,
      uncached_input_tokens: 0,
      output_tokens: 0,
      total_tokens: 0,
      total_usd: 0,
      total_zar: 0,
      input_credits: 0,
      cached_input_credits: 0,
      output_credits: 0,
      total_credits: 0,
    } as UsageTotals,
  );
}

export function accountMatchesFocusedDomains(account: string | undefined) {
  return focusedAccountDomains.some((domain) => (account || "").endsWith(domain));
}

export function totalsForFocusedDomains(report: Pick<UsageReport, "totals" | "by_account"> | undefined) {
  if (!report) return undefined;
  const rows = report.by_account?.filter((row) => accountMatchesFocusedDomains(row.account)) || [];
  if (!rows.length) return report.totals;
  return rows.reduce(
    (totals, row) => {
      totals.input_tokens += Number(row.input_tokens || 0);
      totals.output_tokens += Number(row.output_tokens || 0);
      totals.total_tokens += Number(row.total_tokens || 0);
      totals.total_zar += Number(row.total_zar || 0);
      totals.total_credits += Number(row.total_credits || 0);
      return totals;
    },
    { input_tokens: 0, output_tokens: 0, total_tokens: 0, total_zar: 0, total_usd: 0, input_credits: 0, output_credits: 0, total_credits: 0 } as UsageTotals,
  );
}

export function focusedAccounts(accounts?: Array<{ account: string }>) {
  const matches = accounts?.map((option) => option.account).filter((account) => accountMatchesFocusedDomains(account)) || [];
  return matches.length ? matches : fallbackFocusedAccounts;
}

function localDate(isoDay: string) {
  return new Date(`${isoDay}T00:00:00`);
}

function localIsoDate(date: Date) {
  const year = date.getFullYear();
  const month = String(date.getMonth() + 1).padStart(2, "0");
  const day = String(date.getDate()).padStart(2, "0");
  return `${year}-${month}-${day}`;
}

function weekStartDate(date: Date) {
  const copy = new Date(date);
  const day = copy.getDay() || 7;
  copy.setDate(copy.getDate() - day + 1);
  return localIsoDate(copy);
}

function weekEndDate(weekStart: string) {
  const end = localDate(weekStart);
  end.setDate(end.getDate() + 6);
  return localIsoDate(end);
}

function emptyGroupedRow(key: string, label: string): UsageDay & { label: string } {
    return {
    day: key,
    label,
    input_tokens: 0,
    cached_input_tokens: 0,
    uncached_input_tokens: 0,
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
    events: 0,
    sessions: 0,
    files: 0,
  };
}

function addUsage(target: UsageDay, row: UsageDay) {
  target.input_tokens += Number(row.input_tokens || 0);
  target.cached_input_tokens = Number(target.cached_input_tokens || 0) + Number(row.cached_input_tokens || 0);
  target.uncached_input_tokens = Number(target.uncached_input_tokens || 0) + Number(row.uncached_input_tokens || 0);
  target.output_tokens += Number(row.output_tokens || 0);
  target.reasoning_output_tokens = Number(target.reasoning_output_tokens || 0) + Number(row.reasoning_output_tokens || 0);
  target.total_tokens += Number(row.total_tokens || 0);
  target.total_usd += Number(row.total_usd || 0);
  target.total_zar += Number(row.total_zar || 0);
  target.input_credits += Number(row.input_credits || 0);
  target.cached_input_credits = Number(target.cached_input_credits || 0) + Number(row.cached_input_credits || 0);
  target.output_credits += Number(row.output_credits || 0);
  target.reasoning_output_credits = Number(target.reasoning_output_credits || 0) + Number(row.reasoning_output_credits || 0);
  target.total_credits += Number(row.total_credits || 0);
  target.events = Number(target.events || 0) + Number(row.events || 0);
  target.sessions = Number(target.sessions || 0) + Number(row.sessions || 0);
  target.files = Number(target.files || 0) + Number(row.files || 0);
}

export function groupedUsageRows(rows: UsageDay[], mode: GroupMode) {
  if (mode === "day") {
    return rows.map((row) => ({ ...row, label: row.day.slice(5) }));
  }

  const grouped = new Map<string, UsageDay & { label: string }>();
  for (const row of rows) {
    const date = localDate(row.day);
    const key = mode === "week" ? weekStartDate(date) : row.day.slice(0, 7);
    const label = mode === "week" ? `${key} to ${weekEndDate(key)}` : key;
    const aggregate = grouped.get(key) || emptyGroupedRow(key, label);
    addUsage(aggregate, row);
    grouped.set(key, aggregate);
  }
  return [...grouped.values()].sort((left, right) => left.day.localeCompare(right.day));
}

export function groupedUsageRowsForReport(report: DaysReport | undefined, mode: GroupMode) {
  if (!report) return [];
  if (mode === "week" && report.weeks?.length) return report.weeks;
  if (mode === "month" && report.months?.length) return report.months;
  return groupedUsageRows(report.days || [], mode);
}

export function cacheBackendName(cache: SnapshotCacheStatus | unknown) {
  if (!cache || typeof cache !== "object") return null;
  const backend = (cache as SnapshotCacheStatus).backend;
  if (typeof backend === "string") return backend;
  if (backend && typeof backend === "object" && typeof backend.backend === "string") {
    return backend.backend;
  }
  return null;
}

export function cacheBackendLabel(cache: SnapshotCacheStatus | unknown) {
  const backend = cacheBackendName(cache);
  if (backend) return backend;
  if (!cache || typeof cache !== "object") return "loading";
  return "unknown";
}

export function usesMemoryCache(cache: SnapshotCacheStatus | unknown) {
  return cacheBackendName(cache) === "memory";
}

export type GroupedUsageDay = UsageDay & { label?: string };
export type BreakdownLabelKey = keyof Pick<BreakdownRow, "model" | "effort" | "account">;
