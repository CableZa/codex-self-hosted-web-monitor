import type { DateRange } from "./apiTypes";

export type ChartMode = "line" | "bar";
export type GroupMode = "day" | "week" | "month";
export type AppTab = "dashboard" | "sessions" | "settings";

export function defaultChartModeForRange(range: DateRange): ChartMode {
  const days = Math.max(1, Math.ceil((new Date(range.end_at).getTime() - new Date(range.start_at).getTime()) / 86_400_000));
  return days <= 10 ? "bar" : "line";
}

export function chartModeFromUrl(range: DateRange): ChartMode {
  const value = new URLSearchParams(window.location.search).get("chart");
  if (value === "bar" || value === "bars") return "bar";
  if (value === "line" || value === "lines") return "line";
  return defaultChartModeForRange(range);
}

export function groupModeFromUrl(): GroupMode {
  const value = new URLSearchParams(window.location.search).get("group");
  if (value === "day" || value === "daily") return "day";
  if (value === "week" || value === "weekly") return "week";
  if (value === "month" || value === "monthly") return "month";
  return "day";
}

export function accountsFromUrl() {
  const value = new URLSearchParams(window.location.search).get("accounts");
  if (!value) return [];
  return value.split(",").map((account) => account.trim()).filter(Boolean);
}

export function tabFromUrl(): AppTab {
  const value = new URLSearchParams(window.location.search).get("tab");
  if (value === "settings") return "settings";
  if (value === "sessions") return "sessions";
  return "dashboard";
}

export function writeDashboardStateToUrl(
  range: DateRange,
  groupMode: GroupMode,
  chartMode: ChartMode,
  accounts: string[],
  tab: AppTab = tabFromUrl(),
  replace = false,
) {
  const params = new URLSearchParams(window.location.search);
  params.set("tab", tab);
  params.set("start_at", range.start_at);
  params.set("end_at", range.end_at);
  params.delete("date_from");
  params.delete("date_to");
  params.set("group", groupMode);
  params.set("chart", chartMode);
  if (accounts.length) {
    params.set("accounts", accounts.join(","));
  } else {
    params.delete("accounts");
  }
  const next = `${window.location.pathname}?${params.toString()}`;
  if (replace) {
    window.history.replaceState({}, "", next);
  } else {
    window.history.pushState({}, "", next);
  }
}

export function writeTabToUrl(tab: AppTab) {
  const params = new URLSearchParams(window.location.search);
  params.set("tab", tab);
  window.history.pushState({}, "", `${window.location.pathname}?${params.toString()}`);
}
