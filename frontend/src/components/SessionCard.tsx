import { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { AlertTriangle, ChevronDown, ChevronRight } from "lucide-react";
import type { DateRange, SessionDetail, SessionSummary } from "../lib/apiTypes";
import { fetchSessionDetail } from "../lib/api";
import { compactCredits, fmtCompactNum, formatDateTime } from "../lib/format";
import { formatDuration, formatPercent, signalDescription } from "../lib/sessionDisplay";
import { hasVisibleContextSignal, visibleContextReasons, type SessionSignalThresholds } from "../lib/sessionSignalThresholds";
import { BreakdownTable } from "./DashboardTables";
import { LoaderBlock } from "./DashboardPrimitives";
import { SignalInfoDialog } from "./SessionSignalInfo";

function SessionEventTable({ session, showAccountColumn }: { session: SessionDetail; showAccountColumn: boolean }) {
  if (!session.timeline.length) {
    return <div className="text-sm text-muted">No token events found for this session.</div>;
  }

  return (
    <div className="overflow-x-auto rounded-lg border border-border bg-canvas/60">
      <table className={`${showAccountColumn ? "min-w-[940px]" : "min-w-[820px]"} w-full text-left text-sm`}>
        <thead className="text-xs uppercase text-muted">
          <tr>
            <th className="border-b border-border px-3 py-2">Time</th>
            <th className="border-b border-border px-3 py-2">Model</th>
            {showAccountColumn ? <th className="border-b border-border px-3 py-2">Account</th> : null}
            <th className="border-b border-border px-3 py-2">Effort</th>
            <th className="border-b border-border px-3 py-2">Uncached</th>
            <th className="border-b border-border px-3 py-2">Cached</th>
            <th className="border-b border-border px-3 py-2">Output</th>
            <th className="border-b border-border px-3 py-2">Credits</th>
          </tr>
        </thead>
        <tbody>
          {session.timeline.map((event, index) => (
            <tr key={`${event.timestamp}-${event.path}-${event.model}-${index}`}>
              <td className="border-b border-border/70 px-3 py-2 text-muted">{formatDateTime(event.timestamp)}</td>
              <td className="border-b border-border/70 px-3 py-2">
                <div className="font-semibold text-ink">{event.model}</div>
                {event.priced_model && event.priced_model !== event.model ? (
                  <div className="text-xs text-muted">priced as {event.priced_model}</div>
                ) : null}
              </td>
              {showAccountColumn ? <td className="border-b border-border/70 px-3 py-2 text-muted">{event.account}</td> : null}
              <td className="border-b border-border/70 px-3 py-2 text-muted">{event.effort}</td>
              <td className="border-b border-border/70 px-3 py-2">{fmtCompactNum.format(event.uncached_input_tokens || 0)}</td>
              <td className="border-b border-border/70 px-3 py-2">{fmtCompactNum.format(event.cached_input_tokens || 0)}</td>
              <td className="border-b border-border/70 px-3 py-2">{fmtCompactNum.format(event.output_tokens || 0)}</td>
              <td className="border-b border-border/70 px-3 py-2 font-semibold text-brand">{compactCredits(event.total_credits || 0)}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

export function SessionCard({
  range,
  selectedAccounts,
  showAccountChrome,
  session,
  signalThresholds,
}: {
  range: DateRange;
  selectedAccounts: string[];
  showAccountChrome: boolean;
  session: SessionSummary;
  signalThresholds: SessionSignalThresholds;
}) {
  const [open, setOpen] = useState(false);
  const [showSignalInfo, setShowSignalInfo] = useState(false);
  const detailQuery = useQuery({
    queryKey: ["session-detail", range, selectedAccounts, session.session_id],
    queryFn: () => fetchSessionDetail(range, session.session_id, selectedAccounts),
    enabled: open,
  });
  const detailWarnings = detailQuery.data?.warnings || [];
  const displayTitle = session.display_title || session.first_message || session.session_id;
  const showTitle = displayTitle !== session.session_id;
  const showLastMessage = session.last_message && session.last_message !== displayTitle;
  const showLongContext = hasVisibleContextSignal(session, signalThresholds);
  const contextReasons = visibleContextReasons(session, signalThresholds);

  return (
    <div className="rounded-sm border border-border bg-canvas/70 p-4 shadow-sm">
      {showSignalInfo ? <SignalInfoDialog onClose={() => setShowSignalInfo(false)} thresholds={signalThresholds} /> : null}
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div className="min-w-0">
          {showTitle ? (
            <>
              <div className="break-words text-base font-bold text-ink">{displayTitle}</div>
              <div className="mt-1 truncate font-mono text-xs font-semibold text-muted">{session.session_id}</div>
            </>
          ) : (
            <div className="break-anywhere font-mono text-sm font-semibold text-ink">{session.session_id}</div>
          )}
          {showLastMessage ? <div className="mt-2 break-words text-sm text-muted">Last: {session.last_message}</div> : null}
          {session.summary ? <div className="mt-2 break-words text-sm text-muted">{session.summary}</div> : null}
          <div className="mt-1 flex flex-wrap items-center gap-x-3 gap-y-1 text-xs text-muted">
            <span>{formatDateTime(session.first_seen)} to {formatDateTime(session.last_seen)}</span>
            <span>{formatDuration(session.duration_seconds)}</span>
            <span>{fmtCompactNum.format(session.events || 0)} events</span>
            <span>{fmtCompactNum.format(session.files || 0)} files</span>
            {session.project_name ? <span className="break-anywhere">{session.project_name}</span> : null}
            <span>{formatPercent(session.cache_efficiency || session.cache_hit_ratio || 0)} cache reuse</span>
            {showLongContext ? (
              <span className="font-semibold text-amber-300" title="The session matched one or more context signals. Open the signal explanation for exact thresholds.">
                long context
              </span>
            ) : null}
          </div>
          <div className="mt-2 flex flex-wrap gap-2">
            {showAccountChrome ? session.accounts.map((account) => (
              <span key={account} className="break-anywhere inline-flex max-w-full rounded-sm border border-border bg-panel px-2.5 py-1 text-xs font-semibold text-muted">
                {account}
              </span>
            )) : null}
            {contextReasons.map((reason) => (
              <button
                key={reason}
                type="button"
                title={signalDescription(reason, signalThresholds)}
                className="inline-flex rounded-sm border border-amber-500/50 bg-amber-500/10 px-2.5 py-1 text-xs font-semibold text-amber-200 hover:border-amber-300"
                onClick={() => setShowSignalInfo(true)}
              >
                {reason}
              </button>
            ))}
          </div>
        </div>
        <div className="flex shrink-0 flex-col items-end gap-2">
          <div className="text-right">
            <div className="text-lg font-bold text-brand">{compactCredits(session.total_credits || 0)}</div>
            <div className="text-xs text-muted">{fmtCompactNum.format(session.total_tokens || 0)} tokens</div>
          </div>
          <button
            type="button"
            className="inline-flex items-center gap-2 rounded-sm border border-border bg-panel px-3 py-2 text-sm font-semibold"
            onClick={() => setOpen((value) => !value)}
          >
            {open ? <ChevronDown className="h-4 w-4" /> : <ChevronRight className="h-4 w-4" />}
            {open ? "Hide timeline" : "Show timeline"}
          </button>
        </div>
      </div>

      <div className="mt-4 grid gap-2 sm:grid-cols-4">
        <div className="rounded-sm border border-border bg-panel/80 p-3">
          <div className="text-xs uppercase text-muted">Credits</div>
          <div className="mt-1 text-lg font-bold text-brand">{compactCredits(session.total_credits || 0)}</div>
        </div>
        <div className="rounded-sm border border-border bg-panel/80 p-3">
          <div className="text-xs uppercase text-muted">Uncached input</div>
          <div className="mt-1 text-lg font-bold text-ink">{fmtCompactNum.format(session.uncached_input_tokens || 0)}</div>
        </div>
        <div className="rounded-sm border border-border bg-panel/80 p-3">
          <div className="text-xs uppercase text-muted">Cached input</div>
          <div className="mt-1 text-lg font-bold text-ink">{fmtCompactNum.format(session.cached_input_tokens || 0)}</div>
        </div>
        <div className="rounded-sm border border-border bg-panel/80 p-3">
          <div className="text-xs uppercase text-muted">Output</div>
          <div className="mt-1 text-lg font-bold text-ink">{fmtCompactNum.format(session.output_tokens || 0)}</div>
        </div>
        <div className="rounded-sm border border-border bg-panel/80 p-3 sm:col-span-4">
          <div className="grid gap-2 text-sm text-muted sm:grid-cols-3">
            <div><span className="font-semibold text-ink">{formatPercent(session.cache_efficiency || session.cache_hit_ratio || 0)}</span> input cache reuse</div>
            <div><span className="font-semibold text-ink">{fmtCompactNum.format(session.max_input_tokens || 0)}</span> max input event</div>
            {showLongContext ? <div><span className="font-semibold text-ink">{fmtCompactNum.format(session.long_context_events || 0)}</span> long-context events</div> : null}
          </div>
        </div>
      </div>

      <div className="mt-4">
        <BreakdownTable rows={session.by_model} labelKey="model" totalCredits={session.total_credits || 0} />
      </div>

      {open ? (
        <div className="mt-4 space-y-3">
          {detailQuery.isLoading ? <LoaderBlock label="Loading session timeline" /> : null}
          {detailQuery.isError ? (
            <div className="rounded-lg border border-danger/40 bg-danger/10 p-3 text-sm text-danger">
              {detailQuery.error instanceof Error ? detailQuery.error.message : "Failed to load session timeline"}
            </div>
          ) : null}
          {detailQuery.data ? (
            <>
              {detailWarnings.length ? (
                <div className="rounded-lg border border-amber-500/50 bg-amber-500/10 p-3 text-sm text-amber-100">
                  <div className="mb-2 inline-flex items-center gap-2 font-semibold text-amber-200">
                    <AlertTriangle className="h-4 w-4" />
                    Session warning
                  </div>
                  <ul className="grid gap-1">
                    {detailWarnings.map((warning) => (
                      <li key={warning}>{warning}</li>
                    ))}
                  </ul>
                </div>
              ) : null}
              <SessionEventTable session={detailQuery.data} showAccountColumn={showAccountChrome} />
            </>
          ) : null}
        </div>
      ) : null}
    </div>
  );
}
