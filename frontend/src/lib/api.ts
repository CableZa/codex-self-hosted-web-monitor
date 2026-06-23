import type {
  AccountLimit,
  AccountLimitsReport,
  AccountLimitStatus,
  AccountsReport,
  Alert,
  AuthSnapshotCreate,
  AuthSnapshotResult,
  ChangelogReport,
  DateRange,
  DaysReport,
  RateCard,
  Settings,
  SessionDetail,
  SessionHistoryReport,
  Snapshot,
  UpdateStatus,
  UsageDiagnosticsReport,
  UsageReport,
} from "./apiTypes";

export type * from "./apiTypes";

async function getJson<T>(url: string, options?: RequestInit): Promise<T> {
  const response = await fetch(url, options);
  if (!response.ok) {
    throw new Error(await response.text());
  }
  return response.json() as Promise<T>;
}

function rangeParams(range: DateRange, accounts?: string[]) {
  const params = new URLSearchParams({ start_at: range.start_at, end_at: range.end_at });
  if (accounts?.length) params.set("accounts", accounts.join(","));
  return params;
}

export function fetchSnapshot() {
  return getJson<Snapshot>("/api/snapshot");
}

export function fetchSettings() {
  return getJson<Settings>("/api/settings");
}

export function fetchRateCard() {
  return getJson<RateCard>("/api/rate-card");
}

export function fetchDays(range: DateRange, accounts?: string[]) {
  return getJson<DaysReport>(`/api/days?${rangeParams(range, accounts).toString()}`);
}

export function fetchSummary(range: DateRange, accounts?: string[]) {
  return getJson<UsageReport>(`/api/summary?${rangeParams(range, accounts).toString()}`);
}

export function fetchSessionHistory(range: DateRange, accounts?: string[]) {
  return getJson<SessionHistoryReport>(`/api/sessions?${rangeParams(range, accounts).toString()}`);
}

export function fetchUsageDiagnostics(range: DateRange, accounts?: string[], options?: RequestInit) {
  return getJson<UsageDiagnosticsReport>(`/api/usage-diagnostics?${rangeParams(range, accounts).toString()}`, options);
}

export function fetchSessionDetail(range: DateRange, sessionId: string, accounts?: string[]) {
  return getJson<SessionDetail>(`/api/sessions/${encodeURIComponent(sessionId)}?${rangeParams(range, accounts).toString()}`);
}

export function fetchAccounts() {
  return getJson<AccountsReport>("/api/accounts");
}

export function createAuthSnapshot(snapshot: AuthSnapshotCreate) {
  return getJson<AuthSnapshotResult>("/api/auth-snapshots", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(snapshot),
  });
}

export function fetchChangelog() {
  return getJson<ChangelogReport>("/api/changelog");
}

export function fetchUpdateStatus() {
  return getJson<UpdateStatus>("/api/update-status");
}

export function fetchAccountLimits() {
  return getJson<AccountLimitsReport>("/api/account-limits");
}

export function fetchAlerts() {
  return getJson<Alert[]>("/api/alerts");
}

export function saveSettings(settings: Partial<Settings>) {
  return getJson<Settings>("/api/settings", {
    method: "PUT",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(settings),
  });
}

export function saveAccountLimit(limit: Partial<AccountLimit>) {
  return getJson<{ limit: AccountLimit; status?: AccountLimitStatus | null; status_state?: string }>("/api/account-limits", {
    method: "PUT",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(limit),
  });
}

export function testWebhook() {
  return getJson<{ sent: boolean; reason?: string }>("/api/test-webhook", { method: "POST" });
}
