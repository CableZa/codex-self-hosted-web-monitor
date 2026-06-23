import { useState } from "react";
import { AlertTriangle, ArrowDownWideNarrow, Clock3, Database, GitBranch, Lightbulb, MousePointer2, ShieldCheck, Zap } from "lucide-react";
import type { SessionHistoryReport, SessionSummary, UsageDiagnosticsReport } from "../lib/apiTypes";
import { projectWasteRollups, sessionWasteFindings, type SessionWasteReasonId } from "../lib/dashboardSignals";
import { hasVisibleContextSignal, type SessionSignalThresholds } from "../lib/sessionSignalThresholds";
import { compactCredits, fmtCompactNum, formatDateTime } from "../lib/format";
import { formatPercent, sortSessions } from "../lib/sessionDisplay";
import { SignalInfoButton, SignalInfoDialog } from "./SessionSignalInfo";
import { GlossaryNote } from "./GlossaryNote";

export function SessionInsights({
  diagnostics,
  diagnosticsError,
  diagnosticsFetching,
  sessions,
  signalThresholds,
  visibleSessions,
}: {
  diagnostics?: UsageDiagnosticsReport;
  diagnosticsError: boolean;
  diagnosticsFetching: boolean;
  sessions?: SessionHistoryReport;
  signalThresholds: SessionSignalThresholds;
  visibleSessions: SessionSummary[];
}) {
  const [showSignalInfo, setShowSignalInfo] = useState(false);
  const topSessions = sortSessions(sessions?.sessions || [], "credits", sessions, signalThresholds).slice(0, 5);
  const longContextCount = (sessions?.sessions || []).filter((session) => hasVisibleContextSignal(session, signalThresholds)).length;
  const cacheReport = sessions?.cache_report;

  return (
    <div className="grid gap-3 lg:grid-cols-4">
      {showSignalInfo ? <SignalInfoDialog onClose={() => setShowSignalInfo(false)} thresholds={signalThresholds} /> : null}
      <div className="min-w-0 overflow-hidden rounded-lg border border-border bg-canvas/60 p-3">
        <div className="mb-2 inline-flex items-center gap-2 text-sm font-semibold text-ink">
          <ArrowDownWideNarrow className="h-4 w-4 text-brand" />
          Expensive sessions
        </div>
        <div className="grid gap-2 text-sm">
          {topSessions.length ? topSessions.map((session) => (
            <div key={session.session_id} className="grid min-w-0 grid-cols-[minmax(0,1fr)_auto] items-center gap-3 border-b border-border/60 pb-2 last:border-0 last:pb-0">
              <span className="block min-w-0 truncate text-muted">{session.display_title || session.session_id}</span>
              <span className="font-semibold text-brand">{compactCredits(session.total_credits || 0)}</span>
            </div>
          )) : <div className="text-muted">No expensive sessions in this window.</div>}
        </div>
      </div>

      <div className="min-w-0 overflow-hidden rounded-lg border border-border bg-canvas/60 p-3">
        <div className="mb-2 flex items-center justify-between gap-2">
          <div className="inline-flex items-center gap-2 text-sm font-semibold text-ink">
            <Database className="h-4 w-4 text-brand" />
            Cache efficiency
          </div>
          <SignalInfoButton open={() => setShowSignalInfo(true)} title="Explain cache signals" />
        </div>
        <div className="grid gap-1 text-sm text-muted">
          <div className="flex justify-between gap-3"><span>Input cache reuse</span><span className="font-semibold text-ink">{formatPercent(cacheReport?.cache_efficiency || 0)}</span></div>
          <div className="flex justify-between gap-3"><span>Cached input</span><span>{fmtCompactNum.format(cacheReport?.cached_input_tokens || 0)}</span></div>
          <div className="flex justify-between gap-3"><span>Uncached input</span><span>{fmtCompactNum.format(cacheReport?.uncached_input_tokens || 0)}</span></div>
          <div className="flex justify-between gap-3"><span>Low-cache sessions</span><span>{fmtCompactNum.format(cacheReport?.inefficient_sessions || 0)}</span></div>
        </div>
      </div>

      <div className="min-w-0 overflow-hidden rounded-lg border border-border bg-canvas/60 p-3">
        <div className="mb-2 flex items-center justify-between gap-2">
          <div className="inline-flex items-center gap-2 text-sm font-semibold text-ink">
            <AlertTriangle className="h-4 w-4 text-brand" />
            Context signals
          </div>
          <SignalInfoButton open={() => setShowSignalInfo(true)} title="Explain context signals" />
        </div>
        <div className="grid gap-1 text-sm text-muted">
          <div className="flex justify-between gap-3"><span>Visible sessions</span><span className="font-semibold text-ink">{fmtCompactNum.format(visibleSessions.length)}</span></div>
          <div className="flex justify-between gap-3"><span>Long-context sessions</span><span>{fmtCompactNum.format(longContextCount)}</span></div>
          <div className="flex justify-between gap-3"><span>Max input event</span><span>{fmtCompactNum.format(sessions?.totals.max_input_tokens || 0)}</span></div>
        </div>
      </div>

      <div className="min-w-0 overflow-hidden rounded-lg border border-border bg-canvas/60 p-3">
        <div className="mb-2 flex items-center justify-between gap-2">
          <div className="inline-flex items-center gap-2 text-sm font-semibold text-ink">
            <ShieldCheck className="h-4 w-4 text-brand" />
            Usage accuracy
          </div>
          {diagnosticsFetching ? <span className="text-xs text-muted">checking</span> : null}
        </div>
        <div className="grid gap-1 text-sm text-muted">
          <div className="flex justify-between gap-3"><span>Confidence</span><span className="font-semibold capitalize text-ink">{diagnosticsError ? "unavailable" : diagnostics?.confidence_grade || "checking"}</span></div>
          <div className="flex justify-between gap-3"><span>Files scanned</span><span>{fmtCompactNum.format(Number(diagnostics?.scan.filtered_files || diagnostics?.scan.scanned_files || 0))}</span></div>
          <div className="flex justify-between gap-3"><span>Scan time</span><span>{formatScanMs(diagnostics)}</span></div>
          <div className="flex justify-between gap-3"><span>Prefiltered lines</span><span>{fmtCompactNum.format(prefilterCount(diagnostics))}</span></div>
          <div className="flex justify-between gap-3"><span>Parser skips</span><span>{fmtCompactNum.format(parserSkipCount(diagnostics))}</span></div>
          <div className="flex justify-between gap-3"><span>Tool errors</span><span>{fmtCompactNum.format(Number(diagnostics?.activity.tool_errors || 0))}</span></div>
        </div>
        {diagnostics?.confidence_reasons?.[0] ? (
          <div className="mt-2 truncate text-xs text-muted">{diagnostics.confidence_reasons[0]}</div>
        ) : diagnosticsError ? (
          <div className="mt-2 truncate text-xs text-muted">Usage diagnostics could not be loaded.</div>
        ) : null}
      </div>
    </div>
  );
}

function prefilterCount(diagnostics?: UsageDiagnosticsReport) {
  if (!diagnostics) return 0;
  return Number(diagnostics.parser.usage_lines_prefiltered || 0)
    + Number(diagnostics.parser.metadata_lines_prefiltered || 0);
}

function formatScanMs(diagnostics?: UsageDiagnosticsReport) {
  const ms = Number(diagnostics?.scan.total_scan_ms || diagnostics?.parser.total_scan_ms || 0);
  if (!ms) return "checking";
  if (ms < 1000) return `${fmtCompactNum.format(ms)} ms`;
  return `${(ms / 1000).toFixed(ms < 10_000 ? 1 : 0)} s`;
}

function parserSkipCount(diagnostics?: UsageDiagnosticsReport) {
  if (!diagnostics) return 0;
  return Number(diagnostics.parser.invalid_json_events || 0)
    + Number(diagnostics.parser.non_object_json_events || 0)
    + Number(diagnostics.parser.non_object_payload_events || 0)
    + Number(diagnostics.parser.malformed_usage_events || 0)
    + Number(diagnostics.parser.skipped_subagent_replay_events || 0);
}

export function ProjectAndAccountAudit({ sessions, showAccountAudit }: { sessions?: SessionHistoryReport; showAccountAudit: boolean }) {
  const projects = sessions?.by_project || [];
  const switches = sessions?.account_switches || [];

  return (
    <div className={`grid gap-3 ${showAccountAudit ? "lg:grid-cols-2" : ""}`}>
      <div className="rounded-lg border border-border bg-canvas/60 p-3">
        <div className="mb-2 inline-flex items-center gap-2 text-sm font-semibold text-ink">
          <GitBranch className="h-4 w-4 text-brand" />
          Projects
        </div>
        <div className="grid gap-2 text-sm">
          {projects.length ? projects.slice(0, 8).map((project) => (
            <div key={`${project.project}-${project.project_path || ""}`} className="grid min-w-0 grid-cols-[minmax(0,1fr)_minmax(0,7.5rem)] items-start gap-3 border-b border-border/60 pb-2 last:border-0 last:pb-0">
              <span className="block min-w-0">
                <span className="break-anywhere block font-semibold text-ink">{project.project}</span>
                {project.project_path ? <span className="break-anywhere block text-xs text-muted">{project.project_path}</span> : null}
              </span>
              <span className="block min-w-0 text-right leading-tight">
                <span className="block break-words font-semibold text-brand">{compactCredits(project.total_credits || 0)}</span>
                <span className="block text-xs text-muted">{fmtCompactNum.format(project.sessions || 0)} sessions</span>
              </span>
            </div>
          )) : <div className="text-muted">No project rollups in this window.</div>}
        </div>
      </div>

      {showAccountAudit ? <div className="rounded-lg border border-border bg-canvas/60 p-3">
        <div className="mb-2 inline-flex items-center gap-2 text-sm font-semibold text-ink">
          <Clock3 className="h-4 w-4 text-brand" />
          Account switch audit
        </div>
        <div className="grid gap-2 text-sm">
          {switches.length ? switches.map((item) => (
            <div key={`${item.observed_at}-${item.to_account}`} className="border-b border-border/60 pb-2 last:border-0 last:pb-0">
              <div className="font-semibold text-ink">{formatDateTime(item.observed_at)}</div>
              <div className="text-muted">{item.from_account || "unknown"} to {item.to_account}</div>
            </div>
          )) : <div className="text-muted">No account switches detected in this window.</div>}
        </div>
      </div> : null}
    </div>
  );
}

export function SessionWasteFinder({
  onSelectSession,
  sessions,
  signalThresholds,
  visibleSessions,
  wasteReasonFilter,
}: {
  onSelectSession: (session: SessionSummary) => void;
  sessions?: SessionHistoryReport;
  signalThresholds: SessionSignalThresholds;
  visibleSessions: SessionSummary[];
  wasteReasonFilter?: SessionWasteReasonId | "";
}) {
  const findings = sessionWasteFindings(sessions, visibleSessions, { reasonId: wasteReasonFilter, thresholds: signalThresholds });
  const rollups = projectWasteRollups(sessions, visibleSessions, signalThresholds).slice(0, 4);
  return (
    <div className="grid gap-3 lg:grid-cols-[minmax(0,1.4fr)_minmax(20rem,.6fr)]">
      <div className="rounded-lg border border-border bg-canvas/60 p-3">
        <div className="mb-3 flex flex-wrap items-center justify-between gap-3">
          <div className="inline-flex items-center gap-2 text-sm font-semibold text-ink">
            <Zap className="h-4 w-4 text-accent" />
            Session Waste Finder
          </div>
          <div className="text-xs font-semibold text-muted">{fmtCompactNum.format(findings.length)} finding{findings.length === 1 ? "" : "s"}</div>
        </div>
        {findings.length ? (
          <div className="grid gap-2 xl:grid-cols-2">
            {findings.map((finding) => {
              const title = finding.session.display_title || finding.session.first_message || finding.session.session_id;
              const primaryAction = finding.reasons[0]?.action || "review session";
              return (
                <button
                  key={finding.session.session_id}
                  type="button"
                  className="min-w-0 rounded-md border border-border bg-panel/85 p-3 text-left transition hover:border-brand/60 hover:bg-panel"
                  onClick={() => onSelectSession(finding.session)}
                >
                  <div className="grid min-w-0 grid-cols-[minmax(0,1fr)_auto] gap-3">
                    <div className="min-w-0">
                      <div className="truncate font-semibold text-ink">{title}</div>
                      <div className="mt-1 truncate font-mono text-xs text-muted">{finding.session.session_id}</div>
                    </div>
                    <div className="text-right">
                      <div className="font-bold text-brand">{compactCredits(finding.session.total_credits || 0)}</div>
                      <div className="text-xs text-muted">{fmtCompactNum.format(finding.session.total_tokens || 0)} tokens</div>
                    </div>
                  </div>
                  <div className="mt-3 flex flex-wrap gap-1.5">
                    {finding.reasons.map((reason) => (
                      <span key={reason.id} className="rounded-full border border-accent/35 bg-accent/10 px-2 py-0.5 text-xs font-semibold text-accent">
                        {reason.label}
                      </span>
                    ))}
                  </div>
                  <div className="mt-3 flex flex-wrap items-center gap-2">
                    <span className="inline-flex max-w-full items-center gap-2 rounded-md border border-brand/25 bg-brand/5 px-2.5 py-1.5 text-xs font-semibold text-brand">
                      <Lightbulb className="h-3.5 w-3.5 shrink-0" />
                      <span className="truncate">{primaryAction}</span>
                    </span>
                    <span className="inline-flex items-center gap-1 text-xs font-semibold text-muted">
                      <MousePointer2 className="h-3.5 w-3.5" />
                      Jump to session
                    </span>
                  </div>
                </button>
              );
            })}
          </div>
        ) : (
          <div className="flex items-center justify-between gap-3 rounded-md border border-brand/25 bg-brand/5 p-3 text-sm text-muted">
            <span>No obvious credit leaks found in the visible session set.</span>
            <GlossaryNote label="No obvious credit leaks" note="The visible sessions do not match the configured likely-waste signals for uncached input, cache reuse, output volume, or long-context activity." />
          </div>
        )}
      </div>

      <div className="rounded-lg border border-border bg-canvas/60 p-3">
        <div className="mb-3 inline-flex items-center gap-2 text-sm font-semibold text-ink">
          <GitBranch className="h-4 w-4 text-brand" />
          Project waste rollups
        </div>
        {rollups.length ? (
          <div className="grid gap-2 text-sm">
            {rollups.map((rollup) => (
              <div key={`${rollup.project}-${rollup.projectPath || ""}`} className="rounded-md border border-border bg-panel/80 p-3">
                <div className="grid min-w-0 grid-cols-[minmax(0,1fr)_auto] gap-3">
                  <div className="min-w-0">
                    <div className="break-anywhere font-semibold text-ink">{rollup.project}</div>
                    {rollup.projectPath ? <div className="break-anywhere text-xs text-muted">{rollup.projectPath}</div> : null}
                  </div>
                  <div className="text-right">
                    <div className="font-bold text-brand">{compactCredits(rollup.wasteCredits)}</div>
                    <div className="text-xs text-muted">{fmtCompactNum.format(rollup.sessions)} sessions</div>
                  </div>
                </div>
                <div className="mt-2 flex flex-wrap gap-1.5">
                  {rollup.reasons.slice(0, 3).map((reason) => (
                    <span key={reason.id} className="rounded-full border border-border bg-canvas px-2 py-0.5 text-xs font-semibold text-muted">
                      {reason.label}
                    </span>
                  ))}
                </div>
              </div>
            ))}
          </div>
        ) : (
          <div className="flex items-center justify-between gap-3 rounded-md border border-brand/25 bg-brand/5 p-3 text-sm text-muted">
            <span>No project-level waste concentration in the visible session set.</span>
            <GlossaryNote label="Project waste concentration" note="Project rollups appear when multiple likely-waste sessions cluster under the same project name and path." />
          </div>
        )}
      </div>
    </div>
  );
}
