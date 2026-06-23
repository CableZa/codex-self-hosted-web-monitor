import { AlertTriangle, Bell, Check, CheckCircle2, Database, Flame, Server, UserRoundCheck, WalletCards, X, Zap } from "lucide-react";
import type { AccountLimitStatus, AccountsReport, Alert, SessionHistoryReport, Snapshot, UpdateStatus } from "../lib/apiTypes";
import { attributionIssueCopy, prioritizedAttributionIssues } from "../lib/accountAttribution";
import {
  accountLimitExceeded,
  accountLimitUnderPressure,
  dismissSignal,
  hiddenDismissedSignalCount,
  signalSignature,
  visibleDismissedSignals,
} from "../lib/accountMonitoring";
import { sessionWasteFindings, type SignalSeverity } from "../lib/dashboardSignals";
import type { SessionSignalThresholds } from "../lib/sessionSignalThresholds";
import { cacheBackendLabel } from "../lib/usage";
import { compactCredits, formatDateTime, formatLimitValue } from "../lib/format";
import { useLocalPreference } from "../lib/localPreference";
import { Panel } from "./Panel";
import { Spinner } from "./Spinner";
import { GlossaryNote } from "./GlossaryNote";

const actionSeverityClasses: Record<Exclude<SignalSeverity, "ok">, string> = {
  critical: "border-danger/45 bg-danger/10 text-danger",
  warning: "border-accent/45 bg-accent/10 text-accent",
  info: "border-brand/35 bg-brand/10 text-brand",
};

const actionGlossary: Record<string, string> = {
  attribution: "Attribution review means older usage or the visible Docker history may need a manual baseline snapshot or mount check.",
  burn: "Burn risk follows the focused account and compares its window spend pace against that account's configured weekly limit.",
  waste: "Credit leak checks look for sessions with unusually high uncached input, low cache reuse, high output, or long-context signals.",
  limits: "Account limit review means the focused account is unmonitored or its weekly limit is exceeded or at least 80 percent used in its reset window.",
  alerts: "Recent alerts are global budget, account-limit, or account-burn events emitted by the monitor in the local alert feed.",
};

type ActionItem = {
  id: string;
  signature: string;
  rank: number;
  severity: Exclude<SignalSeverity, "ok">;
  title: string;
  detail: string;
  value?: string;
  icon: React.ReactNode;
  actionLabel?: string;
  actionKey?: "open-settings";
};

type BurnAdvisory = AccountLimitStatus["burn_advisories"][number];

type AttentionStatus = {
  id: keyof typeof actionGlossary;
  signature: string;
  label: string;
  healthy: boolean;
  severity: Exclude<SignalSeverity, "ok">;
};

function burnActionCopy(advisory: BurnAdvisory, focusedAccount: string) {
  if (advisory.id !== "thin-runway") {
    return {
      title: advisory.message,
      detail: focusedAccount ? `${focusedAccount} · ${advisory.label}` : advisory.label,
      value: advisory.value,
    };
  }
  const safeDailyValue = advisory.value.endsWith("/day") ? advisory.value : `${advisory.value}/day`;
  return {
    title: `Safe daily pace: ${safeDailyValue}`,
    detail: focusedAccount ? `${focusedAccount} · ${advisory.message}` : advisory.message,
    value: undefined,
  };
}

function updateStatusAction(updateStatus?: UpdateStatus): ActionItem | null {
  if (!updateStatus) return null;
  if (updateStatus.state === "update_available") {
    return {
      id: "update-available",
      signature: signalSignature("update-available", "warning", updateStatus.latest_version, updateStatus.latest_tag, updateStatus.message),
      rank: 62,
      severity: "warning",
      title: "Update available",
      detail: updateStatus.latest_version ? `Version ${updateStatus.latest_version} is ready locally.` : updateStatus.message || "A newer version is available.",
      value: updateStatus.latest_tag || undefined,
      icon: <Server className="h-4 w-4" />,
    };
  }
  if (updateStatus.state === "update_failed" || updateStatus.state === "checking_failed") {
    return {
      id: `update-${updateStatus.state}`,
      signature: signalSignature(`update-${updateStatus.state}`, updateStatus.error, updateStatus.message),
      rank: 70,
      severity: updateStatus.state === "update_failed" ? "critical" : "warning",
      title: updateStatus.state === "update_failed" ? "Update failed" : "Update check failed",
      detail: updateStatus.error || updateStatus.message || "Review the local update status before redeploying.",
      icon: <Server className="h-4 w-4" />,
    };
  }
  if (updateStatus.state === "updating") {
    return {
      id: "update-running",
      signature: signalSignature("update-running", updateStatus.generated_at, updateStatus.message),
      rank: 45,
      severity: "info",
      title: "Update in progress",
      detail: "The local updater is currently applying changes.",
      icon: <Server className="h-4 w-4" />,
    };
  }
  return null;
}

function attributionAction(accounts?: AccountsReport): ActionItem | null {
  const issue = prioritizedAttributionIssues(accounts?.attribution)[0];
  if (!issue) return null;
  const copy = attributionIssueCopy(issue);
  const facts = [
    issue.earliest_usage_day ? `Visible usage ${issue.earliest_usage_day}` : "",
    issue.first_auth_snapshot_at ? `First snapshot ${formatDateTime(issue.first_auth_snapshot_at)}` : "",
  ].filter(Boolean);
  return {
    id: `attribution-${issue.type}`,
    signature: signalSignature("attribution", issue.type, issue.severity, issue.earliest_usage_day, issue.first_auth_snapshot_at, issue.unknown_usage_totals?.total_credits),
    rank: issue.severity === "critical" ? 97 : issue.severity === "warning" ? 89 : 57,
    severity: issue.severity,
    title: copy.title,
    detail: facts.join(" · ") || issue.detail || copy.detail,
    value: issue.unknown_usage_totals?.total_credits ? compactCredits(issue.unknown_usage_totals.total_credits) : undefined,
    icon: <UserRoundCheck className="h-4 w-4" />,
    actionLabel: "Open Settings",
    actionKey: "open-settings",
  };
}

function buildActionItems({
  accounts,
  advisories,
  alerts,
  focusedAccount,
  focusedStatus,
  sessions,
  sessionsFresh,
  signalThresholds,
  snapshot,
  updateStatus,
}: {
  accounts?: AccountsReport;
  advisories: BurnAdvisory[];
  alerts?: Alert[];
  focusedAccount: string;
  focusedStatus?: AccountLimitStatus;
  sessions?: SessionHistoryReport;
  sessionsFresh: boolean;
  signalThresholds: SessionSignalThresholds;
  snapshot?: Snapshot;
  updateStatus?: UpdateStatus;
}) {
  const items: ActionItem[] = [];
  const attribution = attributionAction(accounts);
  if (attribution) items.push(attribution);
  if (focusedAccount && !focusedStatus) {
    items.push({
      id: `account-limit-missing-${focusedAccount}`,
      signature: signalSignature("account-limit-missing", focusedAccount),
      rank: 84,
      severity: "warning",
      title: `${focusedAccount} has no weekly credit limit`,
      detail: "Add a per-account weekly limit before focused runway and burn guidance can evaluate this account.",
      icon: <WalletCards className="h-4 w-4" />,
      actionLabel: "Open Settings",
      actionKey: "open-settings",
    });
  }
  for (const advisory of advisories) {
    const copy = burnActionCopy(advisory, focusedAccount);
    items.push({
      id: `burn-${focusedAccount || "unknown"}-${advisory.id}`,
      signature: signalSignature("burn", focusedAccount, advisory.id, advisory.severity, advisory.message, advisory.label, advisory.value),
      rank: advisory.severity === "critical" ? 100 : advisory.severity === "warning" ? 82 : 58,
      severity: advisory.severity,
      title: copy.title,
      detail: copy.detail,
      value: copy.value,
      icon: <Flame className="h-4 w-4" />,
    });
  }

  if (focusedStatus && focusedStatus.enabled && (focusedStatus.exceeded || focusedStatus.ratio >= 0.8)) {
    items.push({
      id: `account-limit-${focusedStatus.id}`,
      signature: signalSignature("account-limit", focusedStatus.account, focusedStatus.exceeded, focusedStatus.ratio.toFixed(3), focusedStatus.reset_at),
      rank: focusedStatus.exceeded ? 94 : focusedStatus.ratio >= 0.9 ? 78 : 55,
      severity: focusedStatus.exceeded ? "critical" : focusedStatus.ratio >= 0.9 ? "warning" : "info",
      title: focusedStatus.exceeded ? `${focusedStatus.account} limit exceeded` : `${focusedStatus.account} is near limit`,
      detail: `Window resets ${formatDateTime(focusedStatus.reset_at)}`,
      value: `${Math.round(focusedStatus.ratio * 100)}%`,
      icon: <WalletCards className="h-4 w-4" />,
    });
  }

  for (const finding of sessionWasteFindings(sessionsFresh ? sessions : undefined, undefined, { limit: 2, thresholds: signalThresholds })) {
    const title = finding.session.display_title || finding.session.first_message || finding.session.session_id;
    items.push({
      id: `waste-${finding.session.session_id}`,
      signature: signalSignature("waste", finding.session.session_id, finding.score.toFixed(1), finding.reasons.map((reason) => reason.id).join(","), finding.session.total_credits),
      rank: 50 + Math.min(35, finding.score / 25),
      severity: finding.score >= 300 ? "warning" : "info",
      title: "Likely waste session",
      detail: `${title} · ${finding.reasons.map((reason) => reason.label).join(", ")}`,
      value: compactCredits(finding.session.total_credits || 0),
      icon: <Zap className="h-4 w-4" />,
    });
  }

  const updateAction = updateStatusAction(updateStatus);
  if (updateAction) items.push(updateAction);

  const cache = snapshot?.cache as { ok?: boolean } | undefined;
  if (cache && cache.ok === false) {
    items.push({
      id: "cache-service",
      signature: signalSignature("cache-service", cacheBackendLabel(snapshot?.cache)),
      rank: 52,
      severity: "info",
      title: "Response cache needs attention",
      detail: cacheBackendLabel(snapshot?.cache),
      icon: <Database className="h-4 w-4" />,
    });
  }

  for (const alert of (alerts || []).slice(0, 2)) {
    items.push({
      id: `alert-${alert.id}`,
      signature: signalSignature("alert", alert.id, alert.type, alert.created_at, alert.account, alert.value, alert.current_value, alert.current_credits, alert.projected_exhaustion_label),
      rank: alert.type === "account_burn_alert" ? 90 : 88,
      severity: alert.type === "account_burn_alert" && alert.severity === "critical" ? "critical" : "warning",
      title: alert.type === "account_burn_alert"
        ? `Recent burn alert: ${alert.account}`
        : alert.account
          ? `Recent account alert: ${alert.account}`
          : `Recent ${alert.period} budget alert`,
      detail: formatDateTime(alert.created_at),
      value: alert.type === "account_burn_alert"
        ? alert.value || alert.projected_exhaustion_label || undefined
        : alert.account
          ? formatLimitValue(alert.current_value || 0, alert.metric)
          : compactCredits(alert.current_credits || 0),
      icon: <Bell className="h-4 w-4" />,
    });
  }

  return items.sort((left, right) => right.rank - left.rank).slice(0, 6);
}

export function ActionCenter({
  accounts,
  advisories,
  alerts,
  focusedAccount,
  focusedStatus,
  onOpenSettings,
  sessions,
  sessionsFresh,
  sessionsFetching,
  signalThresholds,
  snapshot,
  updateStatus,
  maxItems = 6,
}: {
  accounts?: AccountsReport;
  advisories: BurnAdvisory[];
  alerts?: Alert[];
  focusedAccount: string;
  focusedStatus?: AccountLimitStatus;
  onOpenSettings: () => void;
  sessions?: SessionHistoryReport;
  sessionsFresh: boolean;
  sessionsFetching: boolean;
  signalThresholds: SessionSignalThresholds;
  snapshot?: Snapshot;
  updateStatus?: UpdateStatus;
  maxItems?: number;
}) {
  const [dismissedAttentionRows, setDismissedAttentionRows] = useLocalPreference<Record<string, string>>("codex-monitor-hidden-attention-rows", {});
  const [dismissedActionItems, setDismissedActionItems] = useLocalPreference<Record<string, string>>("codex-monitor-hidden-action-items", {});
  const items = buildActionItems({ accounts, advisories, alerts, focusedAccount, focusedStatus, sessions, sessionsFresh, signalThresholds, snapshot, updateStatus });
  const wasteFindings = sessionWasteFindings(sessionsFresh ? sessions : undefined, undefined, { thresholds: signalThresholds });
  const hasFocusedAccountGap = Boolean(focusedAccount) && !focusedStatus;
  const hasAccountLimitPressure = accountLimitUnderPressure(focusedStatus);
  const hasExceededAccountLimit = accountLimitExceeded(focusedStatus);
  const attributionIssues = prioritizedAttributionIssues(accounts?.attribution);
  const attentionRows: AttentionStatus[] = [
    {
      id: "attribution",
      signature: signalSignature("attribution", !attributionIssues.length, attributionIssues[0]?.severity || "info", attributionIssues[0]?.type || "", attributionIssues[0]?.earliest_usage_day || ""),
      label: attributionIssues.length ? "Attribution needs review" : "Attribution looks current",
      healthy: !attributionIssues.length,
      severity: attributionIssues[0]?.severity || "info",
    },
    {
      id: "burn",
      signature: signalSignature("burn", !advisories.length && !hasFocusedAccountGap, advisories.map((item) => `${item.id}:${item.severity}:${item.value}`).join(","), focusedAccount, hasFocusedAccountGap),
      label: advisories.length
        ? "Burn risk detected"
        : hasFocusedAccountGap
          ? "Burn guidance needs a weekly limit"
          : "No burn risk detected",
      healthy: !advisories.length && !hasFocusedAccountGap,
      severity: advisories.some((item) => item.severity === "critical") ? "critical" : "warning",
    },
    {
      id: "waste",
      signature: signalSignature("waste", !wasteFindings.length, wasteFindings[0]?.session.session_id || "", wasteFindings[0]?.score?.toFixed(1) || ""),
      label: wasteFindings.length ? "Waste sessions found" : "No obvious credit leaks",
      healthy: !wasteFindings.length,
      severity: "info",
    },
    {
      id: "limits",
      signature: signalSignature("limits", !hasAccountLimitPressure && !hasFocusedAccountGap, focusedAccount, focusedStatus?.ratio?.toFixed(3) || "", focusedStatus?.exceeded || false, hasFocusedAccountGap),
      label: hasFocusedAccountGap
        ? `${focusedAccount} is not monitored yet`
        : hasAccountLimitPressure
          ? "Account limits need review"
          : "Focused account limit within range",
      healthy: !hasAccountLimitPressure && !hasFocusedAccountGap,
      severity: hasFocusedAccountGap ? "warning" : hasExceededAccountLimit ? "critical" : "warning",
    },
    {
      id: "alerts",
      signature: signalSignature("alerts", !(alerts?.length), alerts?.[0]?.id || "", alerts?.length || 0),
      label: alerts?.length ? "Recent alerts in feed" : "No alerts in feed",
      healthy: !(alerts?.length),
      severity: "warning",
    },
  ];
  const visibleItems = visibleDismissedSignals(items, dismissedActionItems).slice(0, maxItems);
  const hiddenItemCount = hiddenDismissedSignalCount(items, dismissedActionItems);
  const visibleRows = visibleDismissedSignals(attentionRows, dismissedAttentionRows);
  const hiddenRowCount = hiddenDismissedSignalCount(attentionRows, dismissedAttentionRows);
  const hiddenSignalCount = hiddenItemCount + hiddenRowCount;

  function dismissAttentionRow(row: AttentionStatus) {
    setDismissedAttentionRows((current) => dismissSignal(current, row));
  }

  function dismissActionItem(item: ActionItem) {
    setDismissedActionItems((current) => dismissSignal(current, item));
  }

  return (
    <Panel
      title="Needs attention"
      meta={sessionsFetching ? <Spinner label="Checking sessions" /> : <span className="text-xs font-semibold text-muted">{visibleItems.length ? `${visibleItems.length} active` : "clear"}</span>}
    >
      {visibleItems.length ? (
        <div className="grid gap-2 lg:grid-cols-2">
          {visibleItems.map((item) => (
            <div key={item.id} className={`rounded-md border p-3 ${actionSeverityClasses[item.severity]}`}>
              <div className="flex items-start gap-3">
                <span className="mt-0.5 shrink-0">{item.icon}</span>
                <div className="min-w-0 flex-1">
                  <div className="break-words font-semibold text-ink">{item.title}</div>
                  <div className="mt-1 break-words text-sm text-muted">{item.detail}</div>
                  {item.actionLabel && item.actionKey === "open-settings" ? (
                    <button
                      type="button"
                      className="mt-2 inline-flex items-center gap-2 rounded-md border border-border/70 bg-panel/70 px-3 py-1.5 text-sm font-semibold text-ink"
                      onClick={onOpenSettings}
                    >
                      {item.actionLabel}
                    </button>
                  ) : null}
                </div>
                <div className="ml-auto flex shrink-0 items-start gap-2">
                  {item.value ? <div className="text-right text-sm font-bold">{item.value}</div> : null}
                  <button
                    type="button"
                    className="inline-flex h-6 w-6 items-center justify-center rounded border border-border/70 bg-panel/70 text-muted hover:border-brand hover:text-brand"
                    onClick={() => dismissActionItem(item)}
                    title={`Hide ${item.title}`}
                  >
                    <X className="h-3.5 w-3.5" />
                    <span className="sr-only">Hide {item.title}</span>
                  </button>
                </div>
              </div>
            </div>
          ))}
        </div>
      ) : hiddenItemCount ? (
        <div className="rounded-md border border-border bg-canvas/60 p-3 text-sm text-muted">
          Active dashboard items are hidden locally.
        </div>
      ) : (
        <div className="rounded-md border border-brand/25 bg-brand/5 p-3 text-sm text-muted">
          No active dashboard items need attention.
        </div>
      )}
      <div className="mt-3 flex flex-wrap items-center justify-between gap-3">
        <div className="text-xs text-muted">
          {hiddenSignalCount
            ? `${hiddenSignalCount} dashboard signal${hiddenSignalCount === 1 ? "" : "s"} hidden locally`
            : "Dashboard signals can be hidden locally. Changed signals will reappear."}
        </div>
        {hiddenSignalCount ? (
          <button
            type="button"
            className="inline-flex items-center gap-2 rounded-md border border-border bg-panel/70 px-3 py-1.5 text-sm font-semibold text-ink"
            onClick={() => {
              setDismissedAttentionRows({});
              setDismissedActionItems({});
            }}
          >
            <Check className="h-4 w-4" />
            Show hidden items
          </button>
        ) : null}
      </div>
      <div className="mt-3 grid gap-2 sm:grid-cols-2 xl:grid-cols-4">
        {visibleRows.map((row) => (
          <div key={row.id} className={`inline-flex min-w-0 items-center gap-2 rounded-md border px-3 py-2 text-sm ${row.healthy ? "border-border bg-canvas/60 text-muted" : actionSeverityClasses[row.severity]}`}>
            {row.healthy ? <CheckCircle2 className="h-4 w-4 shrink-0 text-brand" /> : <AlertTriangle className="h-4 w-4 shrink-0" />}
            <span className="truncate">{row.label}</span>
            <GlossaryNote label={row.label} note={actionGlossary[row.id]} />
            <button
              type="button"
              className="ml-auto inline-flex h-6 w-6 shrink-0 items-center justify-center rounded border border-border/70 bg-panel/70 text-muted hover:border-brand hover:text-brand"
              onClick={() => dismissAttentionRow(row)}
              title={`Hide ${row.label}`}
            >
              <X className="h-3.5 w-3.5" />
              <span className="sr-only">Hide {row.label}</span>
            </button>
          </div>
        ))}
      </div>
    </Panel>
  );
}
