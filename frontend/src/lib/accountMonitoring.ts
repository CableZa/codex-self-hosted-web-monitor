import type { AccountLimitStatus, AccountsReport } from "./apiTypes";
import { confirmedAccountNames, confirmedSnapshots, snapshotAccount } from "./accountAttribution";

export type SignalSeverity = "critical" | "warning" | "info" | "ok";

export type HealthySignalRow = {
  id: string;
  healthy: boolean;
};

export type DismissibleSignal = {
  id: string;
  signature: string;
};

export function latestObservedAccount(report?: AccountsReport) {
  const snapshots = confirmedSnapshots(report);
  const latest = snapshots[snapshots.length - 1];
  return latest ? snapshotAccount(latest) : "";
}

export function monitorAccountOptions(report: AccountsReport | undefined, statuses: AccountLimitStatus[]) {
  const latest = latestObservedAccount(report);
  const confirmed = new Set(confirmedAccountNames(report));
  const ordered = [
    latest,
    ...statuses
      .map((status) => status.account)
      .filter((account) => confirmed.has(account)),
  ].filter(Boolean);
  return [...new Set(ordered)];
}

export function focusedMonitorAccount(
  report: AccountsReport | undefined,
  statuses: AccountLimitStatus[],
  override = "",
) {
  const options = monitorAccountOptions(report, statuses);
  if (override && options.includes(override)) return override;
  return options[0] || "";
}

export function statusForAccount(statuses: AccountLimitStatus[], account: string) {
  return statuses.find((status) => status.account === account);
}

export function burnAdvisoriesForAccount(status?: AccountLimitStatus) {
  return status?.burn_advisories || [];
}

export function accountLimitUnderPressure(status?: AccountLimitStatus) {
  return Boolean(status?.enabled && (status.exceeded || status.ratio >= 0.8));
}

export function accountLimitExceeded(status?: AccountLimitStatus) {
  return Boolean(status?.enabled && status.exceeded);
}

export function signalSignature(...parts: Array<string | number | boolean | null | undefined>) {
  return parts.map((part) => String(part ?? "")).join("::");
}

export function shouldShowMonitorAccountSelector(options: string[]) {
  return options.length > 1;
}

export function visibleDismissedSignals<T extends DismissibleSignal>(rows: T[], dismissed: Record<string, string>) {
  return rows.filter((row) => dismissed[row.id] !== row.signature);
}

export function hiddenDismissedSignalCount<T extends DismissibleSignal>(rows: T[], dismissed: Record<string, string>) {
  return rows.filter((row) => dismissed[row.id] === row.signature).length;
}

export function dismissSignal<T extends DismissibleSignal>(dismissed: Record<string, string>, row: T) {
  if (dismissed[row.id] === row.signature) return dismissed;
  return { ...dismissed, [row.id]: row.signature };
}
