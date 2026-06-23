import { Group as ResizeGroup, Panel as ResizePanel, Separator as ResizeSeparator } from "react-resizable-panels";
import type { DateRange, SessionSummary } from "../lib/apiTypes";
import { compactCredits, fmtCompactNum, formatDateTime } from "../lib/format";
import { formatDuration, formatPercent } from "../lib/sessionDisplay";
import { hasVisibleContextSignal, type SessionSignalThresholds } from "../lib/sessionSignalThresholds";
import { SessionCard } from "./SessionCard";
import { Spinner } from "./Spinner";

function SessionListItem({
  active,
  onSelect,
  session,
  signalThresholds,
  showAccountChrome,
}: {
  active: boolean;
  onSelect: () => void;
  session: SessionSummary;
  signalThresholds: SessionSignalThresholds;
  showAccountChrome: boolean;
}) {
  const displayTitle = session.display_title || session.first_message || session.session_id;
  const showLongContext = hasVisibleContextSignal(session, signalThresholds);
  return (
    <button
      type="button"
      className={`grid w-full gap-2 border p-3 text-left text-sm transition ${active ? "border-brand border-l-4 bg-brand/10 shadow-sm" : "border-border bg-panel/80 hover:border-brand/60 hover:bg-canvas"}`}
      onClick={onSelect}
    >
      <div className="grid min-w-0 grid-cols-[minmax(0,1fr)_auto] gap-3">
        <div className="min-w-0">
          <div className="truncate font-semibold text-ink">{displayTitle}</div>
          <div className="mt-1 truncate font-mono text-xs text-muted">{session.session_id}</div>
        </div>
        <div className="text-right">
          <div className="font-bold text-brand">{compactCredits(session.total_credits || 0)}</div>
          <div className="text-xs text-muted">{fmtCompactNum.format(session.total_tokens || 0)}</div>
        </div>
      </div>
      <div className="flex flex-wrap items-center gap-x-3 gap-y-1 text-xs text-muted">
        <span>{formatDateTime(session.last_seen)}</span>
        <span>{formatDuration(session.duration_seconds)}</span>
        {session.project_name ? <span className="block max-w-full truncate">{session.project_name}</span> : null}
        <span>{formatPercent(session.cache_efficiency || session.cache_hit_ratio || 0)} cache</span>
      </div>
      <div className="flex flex-wrap gap-1.5">
        {showAccountChrome ? session.accounts.slice(0, 2).map((account) => (
          <span key={account} className="break-anywhere max-w-full rounded-sm border border-border bg-canvas px-2 py-0.5 text-xs font-semibold text-muted">
            {account}
          </span>
        )) : null}
        {showLongContext ? (
          <span className="rounded-sm border border-amber-500/50 bg-amber-500/10 px-2 py-0.5 text-xs font-semibold text-amber-200">
            long context
          </span>
        ) : null}
      </div>
    </button>
  );
}

export function SessionSplitPane({
  paneLayout,
  range,
  selectedAccounts,
  selectedSession,
  setPaneLayout,
  setSelectedSessionId,
  sessionRowsCount,
  sessionsFetching,
  signalThresholds,
  showAccountChrome,
  visibleSessions,
}: {
  paneLayout: Record<string, number>;
  range: DateRange;
  selectedAccounts: string[];
  selectedSession?: SessionSummary;
  setPaneLayout: (layout: Record<string, number>) => void;
  setSelectedSessionId: (sessionId: string) => void;
  sessionRowsCount: number;
  sessionsFetching: boolean;
  signalThresholds: SessionSignalThresholds;
  showAccountChrome: boolean;
  visibleSessions: SessionSummary[];
}) {
  return (
    <>
      <div className="hidden min-h-[42rem] overflow-hidden rounded-sm border border-border bg-canvas/50 xl:block">
        <ResizeGroup
          defaultLayout={paneLayout}
          onLayoutChanged={(layout) => setPaneLayout(layout)}
          orientation="horizontal"
        >
          <ResizePanel className="min-w-0" defaultSize="34%" id="sessionList" minSize="24%">
            <div className="flex h-full min-h-[42rem] flex-col">
              <div className="border-b border-border bg-panel/90 p-3">
                <div className="flex items-center justify-between gap-3">
                  <div>
                    <div className="text-sm font-semibold text-ink">Session list</div>
                    <div className="text-xs text-muted">{fmtCompactNum.format(visibleSessions.length)} visible of {fmtCompactNum.format(sessionRowsCount)}</div>
                  </div>
                  {sessionsFetching ? <Spinner label="Updating" /> : null}
                </div>
              </div>
              <div className="min-h-0 flex-1 space-y-2 overflow-y-auto bg-canvas/35 p-2">
                {visibleSessions.map((session) => (
                  <SessionListItem
                    key={session.session_id}
                    active={session.session_id === selectedSession?.session_id}
                    onSelect={() => setSelectedSessionId(session.session_id)}
                    session={session}
                    signalThresholds={signalThresholds}
                    showAccountChrome={showAccountChrome}
                  />
                ))}
              </div>
            </div>
          </ResizePanel>
          <ResizeSeparator className="w-2 border-x border-border bg-panel hover:bg-brand/20" />
          <ResizePanel className="min-w-0" defaultSize="66%" id="sessionDetail" minSize="40%">
            <div className="h-full min-h-[42rem] overflow-y-auto bg-panel/35 p-3">
              {selectedSession ? (
                <SessionCard
                  range={range}
                  selectedAccounts={selectedAccounts}
                  showAccountChrome={showAccountChrome}
                  session={selectedSession}
                  signalThresholds={signalThresholds}
                />
              ) : null}
            </div>
          </ResizePanel>
        </ResizeGroup>
      </div>

      <div className="grid gap-3 xl:hidden">
        <div className="rounded-sm border border-border bg-canvas/50">
          <div className="border-b border-border bg-panel/90 p-3">
            <div className="flex flex-wrap items-center justify-between gap-3">
              <div>
                <div className="text-sm font-semibold text-ink">Session list</div>
                <div className="text-xs text-muted">{fmtCompactNum.format(visibleSessions.length)} visible of {fmtCompactNum.format(sessionRowsCount)}</div>
              </div>
              {sessionsFetching ? <Spinner label="Updating" /> : null}
            </div>
          </div>
          <div className="max-h-[28rem] space-y-2 overflow-y-auto p-2">
            {visibleSessions.map((session) => (
              <SessionListItem
                key={session.session_id}
                active={session.session_id === selectedSession?.session_id}
                onSelect={() => setSelectedSessionId(session.session_id)}
                session={session}
                signalThresholds={signalThresholds}
                showAccountChrome={showAccountChrome}
              />
            ))}
          </div>
        </div>
        {selectedSession ? (
          <SessionCard
            range={range}
            selectedAccounts={selectedAccounts}
            showAccountChrome={showAccountChrome}
            session={selectedSession}
            signalThresholds={signalThresholds}
          />
        ) : null}
      </div>
    </>
  );
}
