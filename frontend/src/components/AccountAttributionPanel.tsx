import { useEffect, useMemo, useState } from "react";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { Check, Clock3, Database, LifeBuoy, RefreshCw, TriangleAlert, UserRoundCheck } from "lucide-react";
import { createAuthSnapshot } from "../lib/api";
import type { AccountsReport, AttributionIssue } from "../lib/apiTypes";
import {
  attributionIssueCopy,
  confirmedAccounts,
  defaultBaselineAccount,
  defaultBaselineTimestampValue,
  fromUtcDateTimeInput,
  latestSnapshotForAccount,
  prioritizedAttributionIssues,
  shouldAutoShowBaselineSnapshotForm,
} from "../lib/accountAttribution";
import { compactCredits, fmtCompactNum, formatDateTime } from "../lib/format";
import { StatusPill } from "./StatusPill";

function issueClasses(severity: AttributionIssue["severity"]) {
  if (severity === "critical") return "border-danger/45 bg-danger/10 text-danger";
  if (severity === "warning") return "border-accent/45 bg-accent/10 text-accent";
  return "border-brand/35 bg-brand/10 text-brand";
}

function issueFacts(issue: AttributionIssue) {
  const facts: string[] = [];
  if (issue.earliest_usage_day) facts.push(`Visible usage starts ${issue.earliest_usage_day}`);
  if (issue.first_auth_snapshot_at) facts.push(`First auth snapshot ${formatDateTime(issue.first_auth_snapshot_at)}`);
  const unknownCredits = issue.unknown_usage_totals?.total_credits || 0;
  const unknownTokens = issue.unknown_usage_totals?.total_tokens || 0;
  if (unknownCredits > 0 || unknownTokens > 0) {
    facts.push(`${compactCredits(unknownCredits)} across ${fmtCompactNum.format(unknownTokens)} tokens`);
  }
  return facts;
}

export function AccountAttributionPanel({ accounts }: { accounts?: AccountsReport }) {
  const queryClient = useQueryClient();
  const confirmed = useMemo(() => confirmedAccounts(accounts), [accounts]);
  const issues = useMemo(() => prioritizedAttributionIssues(accounts?.attribution), [accounts?.attribution]);
  const autoShowBaselineForm = shouldAutoShowBaselineSnapshotForm(accounts);
  const defaultAccount = defaultBaselineAccount(accounts);
  const defaultObservedAt = defaultBaselineTimestampValue(accounts);
  const [selectedAccount, setSelectedAccount] = useState(defaultAccount);
  const [observedAt, setObservedAt] = useState(defaultObservedAt);
  const [showBaselineForm, setShowBaselineForm] = useState(() => autoShowBaselineForm);
  const selectedSnapshot = latestSnapshotForAccount(accounts, selectedAccount);
  const sparseIssue = issues.find((issue) => issue.type === "sparse_visible_history");

  useEffect(() => {
    setSelectedAccount((current) => (confirmed.some((option) => option.account === current) ? current : defaultAccount));
  }, [confirmed, defaultAccount]);

  useEffect(() => {
    setObservedAt((current) => (!current || current === "1970-01-01T00:00" ? defaultObservedAt : current));
  }, [defaultObservedAt]);

  useEffect(() => {
    if (autoShowBaselineForm) {
      setShowBaselineForm(true);
    }
  }, [autoShowBaselineForm]);

  const mutation = useMutation({
    mutationFn: createAuthSnapshot,
    onSuccess: async () => {
      await Promise.all([
        queryClient.invalidateQueries({ queryKey: ["accounts"] }),
        queryClient.invalidateQueries({ queryKey: ["account-limits"] }),
        queryClient.invalidateQueries({ queryKey: ["settings"] }),
        queryClient.invalidateQueries({ queryKey: ["snapshot"] }),
        queryClient.invalidateQueries({ queryKey: ["summary"] }),
        queryClient.invalidateQueries({ queryKey: ["days"] }),
        queryClient.invalidateQueries({ queryKey: ["sessions"] }),
        queryClient.invalidateQueries({ queryKey: ["session-detail"] }),
      ]);
    },
  });

  function submitBaselineSnapshot() {
    if (!selectedSnapshot) return;
    mutation.mutate({
      observed_at: fromUtcDateTimeInput(observedAt),
      account_id: selectedSnapshot.account_id || undefined,
      email: selectedSnapshot.email || undefined,
      name: selectedSnapshot.name || undefined,
      source: "manual",
    });
  }

  const history = accounts?.attribution?.history;
  const canSubmit = Boolean(selectedAccount && observedAt && selectedSnapshot && !mutation.isPending);

  return (
    <section className="rounded-lg border border-border bg-canvas/50 p-4">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div>
          <div className="inline-flex items-center gap-2 text-sm font-semibold text-ink">
            <UserRoundCheck className="h-4 w-4 text-brand" />
            Account attribution
          </div>
          <p className="mt-1 max-w-3xl text-sm text-muted">
            Manual baseline snapshots are explicit. The existing unknown-usage assignment stays available as a fallback.
          </p>
        </div>
        {issues.length ? <StatusPill tone="warn">{issues.length} issue{issues.length === 1 ? "" : "s"}</StatusPill> : <StatusPill>Current</StatusPill>}
      </div>

      <div className="mt-3 grid gap-2 sm:grid-cols-3">
        <div className="rounded-md border border-border bg-panel/70 px-3 py-2 text-sm">
          <div className="text-[0.68rem] font-bold uppercase tracking-normal text-muted">Visible history</div>
          <div className="mt-1 font-semibold text-ink">
            {history?.earliest_usage_day ? `${history.earliest_usage_day} to ${history.latest_usage_day || history.earliest_usage_day}` : "Not detected"}
          </div>
        </div>
        <div className="rounded-md border border-border bg-panel/70 px-3 py-2 text-sm">
          <div className="text-[0.68rem] font-bold uppercase tracking-normal text-muted">First auth snapshot</div>
          <div className="mt-1 font-semibold text-ink">{history?.first_auth_snapshot_at ? formatDateTime(history.first_auth_snapshot_at) : "Not detected"}</div>
        </div>
        <div className="rounded-md border border-border bg-panel/70 px-3 py-2 text-sm">
          <div className="text-[0.68rem] font-bold uppercase tracking-normal text-muted">Visible rollout files</div>
          <div className="mt-1 font-semibold text-ink">{fmtCompactNum.format(history?.visible_rollout_files || 0)}</div>
        </div>
      </div>

      <div className="mt-4 grid gap-4 xl:grid-cols-[1.05fr_.95fr]">
        <div className="grid gap-3">
          {issues.length ? (
            <div className="grid gap-2">
              {issues.map((issue) => {
                const copy = attributionIssueCopy(issue);
                const facts = issueFacts(issue);
                return (
                  <div key={`${issue.type}-${issue.first_auth_snapshot_at || issue.earliest_usage_day || "issue"}`} className={`rounded-md border p-3 ${issueClasses(issue.severity)}`}>
                    <div className="flex flex-wrap items-start justify-between gap-3">
                      <div className="min-w-0">
                        <div className="font-semibold text-ink">{copy.title}</div>
                        <div className="mt-1 text-sm text-muted">{issue.detail || copy.detail}</div>
                      </div>
                      <StatusPill tone={issue.severity === "info" ? "ok" : "warn"}>{issue.severity}</StatusPill>
                    </div>
                    {facts.length ? (
                      <div className="mt-2 flex flex-wrap gap-2 text-xs text-muted">
                        {facts.map((fact) => (
                          <span key={fact} className="rounded-full border border-border/70 bg-panel/70 px-2.5 py-1">{fact}</span>
                        ))}
                      </div>
                    ) : null}
                  </div>
                );
              })}
            </div>
          ) : (
            <div className="rounded-md border border-brand/25 bg-brand/5 p-3 text-sm text-muted">
              Attribution history looks current. Add a manual baseline snapshot only if you need to backfill older usage deliberately.
            </div>
          )}

          {sparseIssue ? (
            <div className="rounded-md border border-border bg-panel/80 p-3 text-sm text-muted">
              <div className="mb-2 inline-flex items-center gap-2 font-semibold text-ink">
                <LifeBuoy className="h-4 w-4 text-brand" />
                Windows and Docker check
              </div>
              <div>Check that `CODEX_HOST_HOME` points to the real Windows `.codex` folder.</div>
              <div className="mt-1">Redeploy with `docker-compose up --build -d monitor scanner valkey` or the repo `./scripts/redeploy` helper.</div>
              <div className="mt-1">Do not use `docker-compose down -v`.</div>
            </div>
          ) : null}

          <div className="rounded-md border border-border bg-panel/80 p-3">
            {showBaselineForm ? (
              <>
                <div className="mb-3 flex flex-wrap items-start justify-between gap-3">
                  <div>
                    <div className="inline-flex items-center gap-2 text-sm font-semibold text-ink">
                      <Clock3 className="h-4 w-4 text-brand" />
                      Manual baseline snapshot
                    </div>
                    <p className="mt-1 text-sm text-muted">Backfill older usage deliberately for a confirmed account.</p>
                  </div>
                  <div className="flex flex-wrap items-center gap-2">
                    {mutation.isSuccess ? (
                      <StatusPill>
                        <Check className="h-3.5 w-3.5" />
                        {mutation.data.inserted ? "Baseline snapshot added" : "Snapshot already matched latest state"}
                      </StatusPill>
                    ) : null}
                    {!autoShowBaselineForm ? (
                      <button
                        type="button"
                        className="inline-flex items-center gap-2 rounded-md border border-border bg-panel/70 px-3 py-2 text-sm font-semibold text-muted hover:text-ink"
                        onClick={() => setShowBaselineForm(false)}
                      >
                        Hide form
                      </button>
                    ) : null}
                  </div>
                </div>
                <div className="grid gap-3 lg:grid-cols-[minmax(0,1fr)_minmax(0,1fr)_auto]">
                  <label className="grid gap-1.5 text-sm text-muted">
                    Confirmed account
                    <select
                      className="rounded-md border border-border bg-canvas px-3 py-2 text-ink disabled:opacity-60"
                      disabled={!confirmed.length}
                      value={selectedAccount}
                      onChange={(event) => setSelectedAccount(event.target.value)}
                    >
                      {!confirmed.length ? <option value="">No confirmed accounts yet</option> : null}
                      {confirmed.map((option) => (
                        <option key={option.account} value={option.account}>{option.account}</option>
                      ))}
                    </select>
                  </label>
                  <label className="grid gap-1.5 text-sm text-muted">
                    Effective date and time (UTC)
                    <input
                      className="rounded-md border border-border bg-canvas px-3 py-2 text-ink disabled:opacity-60"
                      type="datetime-local"
                      value={observedAt}
                      disabled={!confirmed.length}
                      onChange={(event) => setObservedAt(event.target.value)}
                    />
                  </label>
                  <div className="flex items-end gap-2">
                    <button
                      type="button"
                      className="inline-flex w-full items-center justify-center gap-2 rounded-md border border-brand/40 bg-brand px-3 py-2 text-sm font-semibold text-white disabled:opacity-60 dark:text-slate-950"
                      disabled={!canSubmit}
                      onClick={submitBaselineSnapshot}
                    >
                      {mutation.isPending ? <RefreshCw className="h-4 w-4 animate-spin" /> : <Clock3 className="h-4 w-4" />}
                      Add baseline
                    </button>
                  </div>
                </div>
              </>
            ) : (
              <div className="flex flex-wrap items-center justify-between gap-3 rounded-md border border-dashed border-border/80 bg-canvas/65 px-3 py-2.5">
                <div className="min-w-0">
                  <div className="flex flex-wrap items-center gap-2">
                    <div className="inline-flex items-center gap-2 text-sm font-semibold text-ink">
                      <Clock3 className="h-4 w-4 text-brand" />
                      Manual baseline snapshot
                    </div>
                    <span className="rounded-full border border-border/80 bg-panel/80 px-2 py-0.5 text-[0.68rem] font-bold uppercase tracking-normal text-muted">
                      Advanced
                    </span>
                  </div>
                  <p className="mt-1 text-sm text-muted">Only use this when you want to deliberately backfill older usage.</p>
                </div>
                <button
                  type="button"
                  className="inline-flex shrink-0 items-center gap-2 rounded-md border border-border bg-panel/75 px-3 py-2 text-sm font-semibold text-ink transition hover:border-brand/45 hover:bg-brand/10"
                  onClick={() => setShowBaselineForm(true)}
                >
                  <Clock3 className="h-4 w-4" />
                  Open form
                </button>
              </div>
            )}
            {!confirmed.length ? (
              <div className="mt-3 rounded-md border border-accent/35 bg-accent/10 px-3 py-2 text-sm text-accent">
                A login or auth snapshot is needed before a baseline snapshot can target a confirmed account.
              </div>
            ) : null}
            {mutation.isError ? <div className="mt-3 rounded-md border border-danger/35 bg-danger/10 px-3 py-2 text-sm text-danger">Saving the baseline snapshot failed.</div> : null}
          </div>
        </div>

        <div className="grid gap-3">
          <div className="rounded-md border border-border bg-panel/80 p-3">
            <div className="mb-3 inline-flex items-center gap-2 text-sm font-semibold text-ink">
              <Database className="h-4 w-4 text-brand" />
              Confirmed accounts
            </div>
            {confirmed.length ? (
              <div className="overflow-x-auto">
                <table className="w-full min-w-[34rem] text-left text-sm">
                  <thead className="text-xs uppercase text-muted">
                    <tr>
                      <th className="border-b border-border py-2 pr-3">Account</th>
                      <th className="border-b border-border py-2 pr-3">First seen</th>
                      <th className="border-b border-border py-2 pr-3">Last seen</th>
                      <th className="border-b border-border py-2">Source</th>
                    </tr>
                  </thead>
                  <tbody>
                    {confirmed.map((option) => (
                      <tr key={option.account}>
                        <td className="border-b border-border/70 py-2 pr-3 font-semibold text-ink">{option.account}</td>
                        <td className="border-b border-border/70 py-2 pr-3 text-muted">{formatDateTime(option.first_seen)}</td>
                        <td className="border-b border-border/70 py-2 pr-3 text-muted">{formatDateTime(option.last_seen)}</td>
                        <td className="border-b border-border/70 py-2 text-muted">{option.source || "unknown"}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            ) : (
              <div className="text-sm text-muted">No confirmed accounts yet.</div>
            )}
          </div>

          <div className="rounded-md border border-border bg-panel/80 p-3">
            <div className="mb-3 inline-flex items-center gap-2 text-sm font-semibold text-ink">
              <Clock3 className="h-4 w-4 text-brand" />
              Snapshot timeline
            </div>
            {accounts?.snapshots.length ? (
              <div className="overflow-x-auto">
                <table className="w-full min-w-[34rem] text-left text-sm">
                  <thead className="text-xs uppercase text-muted">
                    <tr>
                      <th className="border-b border-border py-2 pr-3">Observed</th>
                      <th className="border-b border-border py-2 pr-3">Account</th>
                      <th className="border-b border-border py-2">Source</th>
                    </tr>
                  </thead>
                  <tbody>
                    {[...(accounts.snapshots || [])]
                      .sort((left, right) => left.observed_at.localeCompare(right.observed_at))
                      .map((snapshot) => (
                        <tr key={`${snapshot.observed_at}-${snapshot.email || snapshot.account_id || "unknown"}`}>
                          <td className="border-b border-border/70 py-2 pr-3 text-muted">{formatDateTime(snapshot.observed_at)}</td>
                          <td className="border-b border-border/70 py-2 pr-3 font-semibold text-ink">{snapshot.email || snapshot.account_id || "unknown"}</td>
                          <td className="border-b border-border/70 py-2 text-muted">{snapshot.source || "unknown"}</td>
                        </tr>
                      ))}
                  </tbody>
                </table>
              </div>
            ) : (
              <div className="flex items-start gap-2 text-sm text-muted">
                <TriangleAlert className="mt-0.5 h-4 w-4 shrink-0 text-accent" />
                <span>No auth snapshots have been recorded yet.</span>
              </div>
            )}
          </div>
        </div>
      </div>
    </section>
  );
}
