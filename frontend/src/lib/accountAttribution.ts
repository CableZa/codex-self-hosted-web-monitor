import type {
  AccountLimitsReport,
  AccountOption,
  AccountsReport,
  AttributionIssue,
  AttributionReport,
  AuthSnapshot,
} from "./apiTypes";

const fallbackBaselineInput = "1970-01-01T00:00";

const severityRank: Record<AttributionIssue["severity"], number> = {
  critical: 3,
  warning: 2,
  info: 1,
};

const issueTypeRank: Record<string, number> = {
  unknown_usage_before_first_snapshot: 3,
  sparse_visible_history: 2,
  late_first_snapshot: 1,
};

export function isConfirmedAccount(option?: AccountOption | null) {
  return Boolean(option && option.account !== "unknown" && option.source !== "usage");
}

export function snapshotAccount(snapshot?: Pick<AuthSnapshot, "email" | "account_id"> | null) {
  return String(snapshot?.email || snapshot?.account_id || "unknown");
}

export function confirmedAccounts(report?: AccountsReport | null) {
  return (report?.accounts || []).filter(isConfirmedAccount);
}

export function confirmedSnapshots(report?: AccountsReport | null) {
  return (report?.snapshots || [])
    .filter((snapshot) => snapshotAccount(snapshot) !== "unknown")
    .sort((left, right) => left.observed_at.localeCompare(right.observed_at));
}

export function latestSnapshotForAccount(report: AccountsReport | undefined, account: string) {
  return [...(report?.snapshots || [])]
    .filter((snapshot) => snapshotAccount(snapshot) === account)
    .sort((left, right) => right.observed_at.localeCompare(left.observed_at))[0];
}

export function confirmedAccountNames(report?: AccountsReport | null) {
  return confirmedAccounts(report).map((option) => option.account);
}

export function defaultBaselineAccount(report?: AccountsReport | null) {
  const earliestSnapshot = confirmedSnapshots(report)[0];
  if (earliestSnapshot) return snapshotAccount(earliestSnapshot);
  return confirmedAccounts(report)[0]?.account || "";
}

export function prioritizedAttributionIssues(attribution?: AttributionReport | null) {
  return [...(attribution?.issues || [])].sort((left, right) => {
    const severityDelta = severityRank[right.severity] - severityRank[left.severity];
    if (severityDelta) return severityDelta;
    return (issueTypeRank[right.type] || 0) - (issueTypeRank[left.type] || 0);
  });
}

export function baselineAttributionIssue(report?: AccountsReport | null) {
  return prioritizedAttributionIssues(report?.attribution).find(
    (issue) => issue.recommended_action === "add_manual_baseline_snapshot",
  );
}

export function shouldAutoShowBaselineSnapshotForm(report?: AccountsReport | null) {
  return Boolean(baselineAttributionIssue(report));
}

export function defaultBaselineTimestampValue(report?: AccountsReport | null) {
  const earliestUsageDay = baselineAttributionIssue(report)?.earliest_usage_day;
  if (earliestUsageDay) return `${earliestUsageDay}T00:00`;
  return "";
}

export function toUtcDateTimeInput(value?: string | null) {
  if (!value) return fallbackBaselineInput;
  const parsed = new Date(value);
  if (Number.isNaN(parsed.getTime())) return fallbackBaselineInput;
  const year = parsed.getUTCFullYear();
  const month = String(parsed.getUTCMonth() + 1).padStart(2, "0");
  const day = String(parsed.getUTCDate()).padStart(2, "0");
  const hour = String(parsed.getUTCHours()).padStart(2, "0");
  const minute = String(parsed.getUTCMinutes()).padStart(2, "0");
  return `${year}-${month}-${day}T${hour}:${minute}`;
}

export function fromUtcDateTimeInput(value: string) {
  return value ? `${value}:00+00:00` : "1970-01-01T00:00:00+00:00";
}

export function attributionIssueCopy(issue: AttributionIssue) {
  switch (issue.type) {
    case "unknown_usage_before_first_snapshot":
      return {
        title: "Older usage may be unattributed",
        detail: "Add a backdated baseline snapshot to assign older usage to a confirmed account.",
      };
    case "late_first_snapshot":
      return {
        title: "Auth snapshots started late",
        detail: "A manual baseline snapshot can fill the gap before the first confirmed login snapshot.",
      };
    case "sparse_visible_history":
      return {
        title: "Visible history looks incomplete",
        detail: "The container may not be seeing the full Windows Codex history mount.",
      };
    default:
      return {
        title: "Attribution needs review",
        detail: issue.detail || "Review the current account attribution history.",
      };
  }
}

export function unconfirmedAccountLimits(report?: AccountLimitsReport | null, accounts?: AccountsReport | null) {
  const confirmed = new Set(confirmedAccountNames(accounts));
  return (report?.limits || []).filter((limit) => !confirmed.has(limit.account));
}

export function editableAccountLimit(report: AccountLimitsReport | undefined, account: string) {
  return report?.limits.find((limit) => limit.account === account);
}
