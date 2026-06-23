import type { Snapshot, UsageReport } from "./apiTypes";

export type SnapshotPeriod = "today" | "week" | "month";

export function snapshotReport(snapshot: Snapshot | undefined, period: SnapshotPeriod): UsageReport | undefined {
  return snapshot?.reports?.[period];
}

export function snapshotReportsReady(snapshot?: Snapshot) {
  return Boolean(snapshot?.reports?.today && snapshot?.reports?.week && snapshot?.reports?.month);
}

export function snapshotRuntimeError(snapshot?: Snapshot) {
  const message = snapshot?.error?.trim();
  return message ? new Error(message) : null;
}

export function snapshotBootstrapPending({
  rangeTimezoneReady,
  queryError,
  runtimeError,
}: {
  rangeTimezoneReady: boolean;
  queryError?: Error | null;
  runtimeError?: Error | null;
}) {
  return !rangeTimezoneReady && !queryError && !runtimeError;
}

export function snapshotDataPending({
  reportsReady,
  queryError,
  runtimeError,
}: {
  reportsReady: boolean;
  queryError?: Error | null;
  runtimeError?: Error | null;
}) {
  return !reportsReady && !queryError && !runtimeError;
}
