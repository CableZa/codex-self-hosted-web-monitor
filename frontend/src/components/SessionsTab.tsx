import { useEffect, useRef, type Dispatch, type SetStateAction } from "react";
import type { AccountsReport, DateRange, SessionHistoryReport, UsageDiagnosticsReport } from "../lib/apiTypes";
import type { Preset } from "../lib/dateRange";
import { sessionMatchesWasteReason, type SessionWasteReasonId } from "../lib/dashboardSignals";
import { hasVisibleContextSignal, type SessionSignalThresholds } from "../lib/sessionSignalThresholds";
import { sessionSearchText, sortSessions } from "../lib/sessionDisplay";
import { useLocalPreference } from "../lib/localPreference";
import { LoaderBlock } from "./DashboardPrimitives";
import { FilterControls, SessionAnalyticsControls } from "./SessionFilters";
import { ProjectAndAccountAudit, SessionInsights, SessionWasteFinder } from "./SessionInsights";
import { SessionSplitPane } from "./SessionSplitPane";
import { Panel } from "./Panel";
import { DataWarning } from "./DataWarning";
import { SessionSummaryStrip } from "./SessionSummaryStrip";

const defaultPaneLayout = {
  sessionDetail: 66,
  sessionList: 34,
};

function isSessionPaneLayout(value: unknown): value is Record<string, number> {
  if (!value || typeof value !== "object" || Array.isArray(value)) return false;
  const layout = value as Record<string, unknown>;
  return Number.isFinite(layout.sessionDetail) && Number.isFinite(layout.sessionList);
}

export function SessionsTab({
  accounts,
  accountsLoading,
  applyAccounts,
  applyRange,
  draftRange,
  focusedMode,
  range,
  rangeError,
  selectedAccounts,
  setDraftRange,
  sessions,
  diagnostics,
  diagnosticsError,
  diagnosticsFetching,
  sessionsFetching,
  sessionsLoading,
  signalThresholds,
  timezone,
}: {
  accounts?: AccountsReport;
  accountsLoading: boolean;
  applyAccounts: (accounts: string[]) => void;
  applyRange: (range: DateRange, options?: { preset?: Preset }) => void;
  draftRange: DateRange;
  focusedMode: boolean;
  range: DateRange;
  rangeError: string;
  selectedAccounts: string[];
  setDraftRange: Dispatch<SetStateAction<DateRange>>;
  sessions?: SessionHistoryReport;
  diagnostics?: UsageDiagnosticsReport;
  diagnosticsError: boolean;
  diagnosticsFetching: boolean;
  sessionsFetching: boolean;
  sessionsLoading: boolean;
  signalThresholds: SessionSignalThresholds;
  timezone: string;
}) {
  const sessionWarnings = sessions?.warnings || [];
  const [search, setSearch] = useLocalPreference("codex-monitor-session-search", "");
  const [sortMode, setSortMode] = useLocalPreference("codex-monitor-session-sort", "recent");
  const [modelFilter, setModelFilter] = useLocalPreference("codex-monitor-session-model", "");
  const [projectFilter, setProjectFilter] = useLocalPreference("codex-monitor-session-project", "");
  const [accountFilter, setAccountFilter] = useLocalPreference("codex-monitor-session-account", "");
  const [longContextOnly, setLongContextOnly] = useLocalPreference("codex-monitor-session-long-context", false);
  const [uncachedHeavyOnly, setUncachedHeavyOnly] = useLocalPreference("codex-monitor-session-low-cache", false);
  const [wasteReasonFilter, setWasteReasonFilter] = useLocalPreference<SessionWasteReasonId | "">("codex-monitor-session-waste-reason", "");
  const [selectedSessionId, setSelectedSessionId] = useLocalPreference("codex-monitor-selected-session", "");
  const [paneLayout, setPaneLayout] = useLocalPreference<Record<string, number>>(
    "codex-monitor-session-panes",
    defaultPaneLayout,
    isSessionPaneLayout,
  );
  const sessionRows = sessions?.sessions || [];
  const modelOptions = Array.from(new Set(sessionRows.flatMap((session) => session.by_model.map((row) => row.model)))).sort();
  const projectOptions = Array.from(new Set(sessionRows.map((session) => session.project_name).filter(Boolean) as string[])).sort();
  const accountOptions = Array.from(new Set(sessionRows.flatMap((session) => session.accounts))).sort();
  const knownAccounts = (accounts?.accounts || []).map((account) => account.account);
  const singleAccountLabel = knownAccounts.length === 1 ? knownAccounts[0] : "";
  const showAccountChrome = !singleAccountLabel;
  const scopeLabel = focusedMode
    ? "Focused accounts"
    : singleAccountLabel || (selectedAccounts.length ? `${selectedAccounts.length} selected accounts` : "All accounts");
  const query = search.trim().toLowerCase();
  const splitPaneRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (singleAccountLabel && accountFilter) setAccountFilter("");
  }, [accountFilter, setAccountFilter, singleAccountLabel]);

  const visibleSessions = sortSessions(
    sessionRows.filter((session) => {
      if (query && !sessionSearchText(session).includes(query)) return false;
      if (modelFilter && !session.by_model.some((row) => row.model === modelFilter)) return false;
      if (projectFilter && session.project_name !== projectFilter) return false;
      if (accountFilter && !session.accounts.includes(accountFilter)) return false;
      if (longContextOnly && !hasVisibleContextSignal(session, signalThresholds)) return false;
      if (uncachedHeavyOnly && !((session.uncached_input_tokens || 0) >= signalThresholds.lowCacheMinUncachedTokens && (session.cache_efficiency || session.cache_hit_ratio || 0) <= signalThresholds.lowCacheMaxReuseRatio)) return false;
      if (!sessionMatchesWasteReason(session, sessions, wasteReasonFilter, signalThresholds)) return false;
      return true;
    }),
    sortMode,
    sessions,
    signalThresholds,
  );
  const selectedSession = visibleSessions.find((session) => session.session_id === selectedSessionId) || visibleSessions[0];

  useEffect(() => {
    if (!visibleSessions.length) return;
    if (visibleSessions.some((session) => session.session_id === selectedSessionId)) return;
    setSelectedSessionId(visibleSessions[0].session_id);
  }, [selectedSessionId, setSelectedSessionId, visibleSessions]);

  function selectWasteSession(session: SessionHistoryReport["sessions"][number]) {
    setSelectedSessionId(session.session_id);
    if (query) setSearch("");
    if (modelFilter && !session.by_model.some((row) => row.model === modelFilter)) setModelFilter("");
    if (projectFilter && session.project_name !== projectFilter) setProjectFilter("");
    if (accountFilter && !session.accounts.includes(accountFilter)) setAccountFilter("");
    if (longContextOnly && !hasVisibleContextSignal(session, signalThresholds)) setLongContextOnly(false);
    if (uncachedHeavyOnly && !((session.uncached_input_tokens || 0) >= signalThresholds.lowCacheMinUncachedTokens && (session.cache_efficiency || session.cache_hit_ratio || 0) <= signalThresholds.lowCacheMaxReuseRatio)) setUncachedHeavyOnly(false);
    if (!sessionMatchesWasteReason(session, sessions, wasteReasonFilter, signalThresholds)) setWasteReasonFilter("");
    window.setTimeout(() => splitPaneRef.current?.scrollIntoView({ block: "start", behavior: "smooth" }), 0);
  }

  return (
    <Panel title="Session History" meta={<span>{sessions?.cache?.hit ? "cache hit" : sessionsFetching ? "loading" : "fresh"}</span>}>
      <div className="space-y-4">
        <DataWarning warnings={sessionWarnings} />

        <SessionSummaryStrip
          scopeLabel={scopeLabel}
          sessionRowsCount={sessionRows.length}
          sessions={sessions}
          sessionsFetching={sessionsFetching}
          visibleCount={visibleSessions.length}
        />

        <SessionInsights
          diagnostics={diagnostics}
          diagnosticsError={diagnosticsError}
          diagnosticsFetching={diagnosticsFetching}
          sessions={sessions}
          signalThresholds={signalThresholds}
          visibleSessions={visibleSessions}
        />
        <SessionWasteFinder
          onSelectSession={selectWasteSession}
          sessions={sessions}
          signalThresholds={signalThresholds}
          visibleSessions={visibleSessions}
          wasteReasonFilter={wasteReasonFilter}
        />
        <ProjectAndAccountAudit sessions={sessions} showAccountAudit={showAccountChrome} />

        <FilterControls
          accounts={accounts}
          accountsLoading={accountsLoading}
          applyAccounts={applyAccounts}
          applyRange={applyRange}
          draftRange={draftRange}
          focusedMode={focusedMode}
          rangeError={rangeError}
          singleAccountLabel={singleAccountLabel}
          selectedAccounts={selectedAccounts}
          setDraftRange={setDraftRange}
          timezone={timezone}
        />

        <SessionAnalyticsControls
          accountFilter={accountFilter}
          accounts={accountOptions}
          longContextOnly={longContextOnly}
          modelFilter={modelFilter}
          models={modelOptions}
          projectFilter={projectFilter}
          projects={projectOptions}
          search={search}
          setAccountFilter={setAccountFilter}
          setLongContextOnly={setLongContextOnly}
          setModelFilter={setModelFilter}
          setProjectFilter={setProjectFilter}
          setSearch={setSearch}
          showAccountFilter={showAccountChrome}
          setSortMode={setSortMode}
          setUncachedHeavyOnly={setUncachedHeavyOnly}
          setWasteReasonFilter={setWasteReasonFilter}
          signalThresholds={signalThresholds}
          sortMode={sortMode}
          uncachedHeavyOnly={uncachedHeavyOnly}
          wasteReasonFilter={wasteReasonFilter}
        />

        {sessionsLoading ? <LoaderBlock label="Loading session history" /> : null}

        {!sessionsLoading && !(sessions?.sessions.length || 0) ? (
          <div className="rounded-lg border border-brand/25 bg-brand/5 p-4 text-sm text-muted">No session activity in this window.</div>
        ) : null}

        {!sessionsLoading && (sessions?.sessions.length || 0) > 0 && !visibleSessions.length ? (
          <div className="rounded-lg border border-brand/25 bg-brand/5 p-4 text-sm text-muted">No sessions match the current filters.</div>
        ) : null}

        {visibleSessions.length ? (
          <div ref={splitPaneRef}>
            <SessionSplitPane
              paneLayout={paneLayout}
              range={range}
              selectedAccounts={selectedAccounts}
              selectedSession={selectedSession}
              setPaneLayout={setPaneLayout}
              setSelectedSessionId={setSelectedSessionId}
              sessionRowsCount={sessionRows.length}
              sessionsFetching={sessionsFetching}
              signalThresholds={signalThresholds}
              showAccountChrome={showAccountChrome}
              visibleSessions={visibleSessions}
            />
          </div>
        ) : null}
      </div>
    </Panel>
  );
}
