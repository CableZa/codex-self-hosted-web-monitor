import { useEffect, useMemo, useRef, useState, type ReactNode } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { Activity, Clock3, LayoutDashboard, RefreshCw, ScrollText, Settings as SettingsIcon, TriangleAlert, X } from "lucide-react";
import { StatusPill } from "./components/StatusPill";
import { DashboardTab } from "./components/DashboardTab";
import { SessionsTab } from "./components/SessionsTab";
import { SettingsTab } from "./components/SettingsTab";
import { ChangelogDialog } from "./components/ChangelogDialog";
import { DataLoadingOverlay, ErrorBlock, QueryStateBar } from "./components/DashboardPrimitives";
import { useLocalPreference } from "./lib/localPreference";
import {
  fetchAccounts,
  fetchAccountLimits,
  fetchAlerts,
  fetchChangelog,
  fetchDays,
  fetchRateCard,
  fetchSettings,
  fetchSnapshot,
  fetchSummary,
  fetchSessionHistory,
  fetchUpdateStatus,
  fetchUsageDiagnostics,
  type DateRange,
} from "./lib/api";
import { defaultTimeZone, formatRangeBound, rangeFromUrl, rangeUrlMode, rangesEqual, validateRange, type Preset } from "./lib/dateRange";
import {
  accountsFromUrl,
  chartModeFromUrl,
  groupModeFromUrl,
  tabFromUrl,
  writeDashboardStateToUrl,
  writeTabToUrl,
  type AppTab,
  type ChartMode,
  type GroupMode,
} from "./lib/dashboardState";
import {
  cacheBackendLabel,
  focusedAccounts,
  groupedUsageRowsForReport,
  rangeTotals,
  usesMemoryCache,
} from "./lib/usage";
import { formatDateTime } from "./lib/format";
import { sessionSignalThresholds } from "./lib/sessionSignalThresholds";
import { snapshotBootstrapPending, snapshotDataPending, snapshotReportsReady, snapshotRuntimeError } from "./lib/snapshotState";

const navItems: Array<{ id: AppTab; label: string; icon: ReactNode }> = [
  { id: "dashboard", label: "Dashboard", icon: <LayoutDashboard className="h-4 w-4" /> },
  { id: "sessions", label: "Sessions", icon: <Activity className="h-4 w-4" /> },
  { id: "settings", label: "Settings", icon: <SettingsIcon className="h-4 w-4" /> },
];

function normalizedUiTheme(value?: string) {
  return value === "classic" ? "classic" : "catppuccin";
}

type RuntimeWindow = Window & {
  __codexAssetFailure?: boolean;
};

export function App() {
  const [range, setRange] = useState<DateRange>(rangeFromUrl);
  const [draftRange, setDraftRange] = useState<DateRange>(range);
  const [chartMode, setChartMode] = useState<ChartMode>(() => chartModeFromUrl(range));
  const [groupMode, setGroupMode] = useState<GroupMode>(groupModeFromUrl);
  const [selectedAccounts, setSelectedAccounts] = useState<string[]>(accountsFromUrl);
  const [activeTab, setActiveTab] = useState<AppTab>(tabFromUrl);
  const [rangeMode, setRangeMode] = useState(rangeUrlMode);
  const [showChangelog, setShowChangelog] = useState(false);
  const [reloadNotice, setReloadNotice] = useState<string | null>(null);
  const [memoryCacheWarningDismissed, setMemoryCacheWarningDismissed] = useLocalPreference("codex-monitor-memory-cache-warning-dismissed", false);
  const loadedVersionRef = useRef<string | null>(null);
  const eventSourceHadErrorRef = useRef(false);
  const queryClient = useQueryClient();

  const rangeError = validateRange(draftRange);
  const snapshot = useQuery({ queryKey: ["snapshot"], queryFn: fetchSnapshot });
  const settings = useQuery({ queryKey: ["settings"], queryFn: fetchSettings });
  const rateCard = useQuery({ queryKey: ["rate-card"], queryFn: fetchRateCard });
  const accounts = useQuery({ queryKey: ["accounts"], queryFn: fetchAccounts });
  const accountLimits = useQuery({ queryKey: ["account-limits"], queryFn: fetchAccountLimits });
  const updateStatus = useQuery({ queryKey: ["update-status"], queryFn: fetchUpdateStatus, staleTime: 60_000 });
  const timezone = snapshot.data?.timezone || defaultTimeZone;
  const expectedRange = useMemo(() => {
    if (!snapshot.data?.timezone || rangeMode === "datetime") return range;
    return rangeFromUrl(snapshot.data.timezone);
  }, [range, rangeMode, snapshot.data?.timezone]);
  const rangeTimezoneReady = rangeMode === "datetime" || (Boolean(snapshot.data?.timezone) && rangesEqual(range, expectedRange));
  const focusedMode = settings.data?.dashboard_mode === "focused";
  const signalThresholds = useMemo(() => sessionSignalThresholds(settings.data), [settings.data]);
  const singleKnownAccount = !focusedMode && accounts.data?.accounts.length === 1 ? accounts.data.accounts[0] : null;
  const effectiveAccounts = focusedMode ? focusedAccounts(accounts.data?.accounts) : singleKnownAccount && !selectedAccounts.length ? [] : selectedAccounts;
  const days = useQuery({
    queryKey: ["days", range, effectiveAccounts],
    queryFn: () => fetchDays(range, effectiveAccounts),
    enabled: rangeTimezoneReady,
    placeholderData: (previousData) => previousData,
  });
  const summary = useQuery({
    queryKey: ["summary", range, effectiveAccounts],
    queryFn: () => fetchSummary(range, effectiveAccounts),
    enabled: rangeTimezoneReady,
    placeholderData: (previousData) => previousData,
  });
  const sessions = useQuery({
    queryKey: ["sessions", range, effectiveAccounts],
    queryFn: () => fetchSessionHistory(range, effectiveAccounts),
    enabled: rangeTimezoneReady && (activeTab === "sessions" || activeTab === "dashboard"),
    placeholderData: (previousData) => previousData,
  });
  const diagnostics = useQuery({
    queryKey: ["usage-diagnostics", range, effectiveAccounts],
    queryFn: ({ signal }) => fetchUsageDiagnostics(range, effectiveAccounts, { signal }),
    enabled: rangeTimezoneReady && activeTab === "sessions",
    placeholderData: (previousData) => previousData,
    retry: false,
    staleTime: 60_000,
    gcTime: 10 * 60_000,
  });
  const alerts = useQuery({ queryKey: ["alerts"], queryFn: fetchAlerts });
  const changelog = useQuery({ queryKey: ["changelog"], queryFn: fetchChangelog, enabled: showChangelog });
  const sessionsLoading = activeTab === "sessions" && sessions.isLoading;
  const sessionsFetching = activeTab === "sessions" && sessions.isFetching;
  const sessionsError = activeTab === "sessions" ? sessions.error : null;
  const snapshotLogicalError = snapshotRuntimeError(snapshot.data);
  const snapshotReady = snapshotReportsReady(snapshot.data);
  const isLoading = snapshot.isLoading || settings.isLoading || accounts.isLoading || accountLimits.isLoading || updateStatus.isLoading || days.isLoading || summary.isLoading || alerts.isLoading || rateCard.isLoading || sessionsLoading;
  const isFetching = snapshot.isFetching || settings.isFetching || accounts.isFetching || accountLimits.isFetching || updateStatus.isFetching || days.isFetching || summary.isFetching || alerts.isFetching || rateCard.isFetching || sessionsFetching;
  const firstError = snapshotLogicalError || snapshot.error || settings.error || accounts.error || accountLimits.error || updateStatus.error || days.error || summary.error || alerts.error || rateCard.error || sessionsError;
  const dashboardRangeBootstrapping = activeTab === "dashboard" && snapshotBootstrapPending({
    rangeTimezoneReady,
    queryError: snapshot.error,
    runtimeError: snapshotLogicalError,
  });
  const dashboardSnapshotBusy = activeTab === "dashboard" && snapshotDataPending({
    reportsReady: snapshotReady,
    queryError: snapshot.error,
    runtimeError: snapshotLogicalError,
  });
  const dashboardDataBusy = activeTab === "dashboard" && (
    dashboardRangeBootstrapping ||
    dashboardSnapshotBusy ||
    (days.isLoading && !days.data) ||
    (summary.isLoading && !summary.data)
  );
  const sessionsDataBusy = activeTab === "sessions" && sessionsLoading && !sessions.data;
  const dataOverlayVisible = dashboardDataBusy || sessionsDataBusy;

  useEffect(() => {
    document.documentElement.dataset.uiTheme = normalizedUiTheme(settings.data?.ui_theme);
  }, [settings.data?.ui_theme]);

  useEffect(() => {
    const listener = () => {
      const nextMode = rangeUrlMode();
      const next = rangeFromUrl(nextMode === "datetime" ? defaultTimeZone : timezone);
      setRange(next);
      setDraftRange(next);
      setChartMode(chartModeFromUrl(next));
      setGroupMode(groupModeFromUrl());
      setSelectedAccounts(accountsFromUrl());
      setActiveTab(tabFromUrl());
      setRangeMode(nextMode);
    };
    window.addEventListener("popstate", listener);
    return () => window.removeEventListener("popstate", listener);
  }, [timezone]);

  useEffect(() => {
    if (!snapshot.data?.timezone || rangeMode === "datetime") return;
    if (rangesEqual(expectedRange, range)) return;
    setRange(expectedRange);
    setDraftRange(expectedRange);
    setChartMode(chartModeFromUrl(expectedRange));
  }, [expectedRange, range, rangeMode, snapshot.data?.timezone]);

  useEffect(() => {
    if (rangeError || rangesEqual(draftRange, range)) return;
    const timer = window.setTimeout(() => {
      setRange(draftRange);
      setRangeMode("datetime");
      writeDashboardStateToUrl(draftRange, groupMode, chartMode, selectedAccounts, activeTab, true);
    }, 500);
    return () => window.clearTimeout(timer);
  }, [activeTab, chartMode, draftRange, groupMode, range, rangeError, selectedAccounts]);

  useEffect(() => {
    if (!singleKnownAccount || !selectedAccounts.length) return;
    if (selectedAccounts.some((account) => account !== singleKnownAccount.account)) return;
    setSelectedAccounts([]);
    writeDashboardStateToUrl(range, groupMode, chartMode, [], activeTab, true);
  }, [activeTab, chartMode, groupMode, range, selectedAccounts, singleKnownAccount]);

  useEffect(() => {
    const runtimeWindow = window as RuntimeWindow;
    if (runtimeWindow.__codexAssetFailure) {
      setReloadNotice("A dashboard asset failed to load. Reload to fetch the current local bundle.");
    }
    const listener = (event: Event) => {
      const target = event.target as HTMLElement | null;
      if (target?.tagName === "SCRIPT" || target?.tagName === "LINK") {
        setReloadNotice("A dashboard asset failed to load. Reload to fetch the current local bundle.");
      }
    };
    window.addEventListener("error", listener, true);
    return () => window.removeEventListener("error", listener, true);
  }, []);

  useEffect(() => {
    const version = snapshot.data?.version;
    if (!version) return;
    if (!loadedVersionRef.current) {
      loadedVersionRef.current = version;
      return;
    }
    if (loadedVersionRef.current !== version) {
      setReloadNotice(`Version ${version} is now running. Reload to use the matching dashboard bundle.`);
    }
  }, [snapshot.data?.version]);

  useEffect(() => {
    const events = new EventSource("/api/events");
    const invalidateQueries = (queryKeys: string[]) => {
      for (const queryKey of queryKeys) {
        void queryClient.invalidateQueries({ queryKey: [queryKey] });
      }
    };
    const invalidateDashboardData = () => {
      invalidateQueries(["snapshot", "accounts", "account-limits", "alerts", "days", "summary", "sessions", "usage-diagnostics", "update-status"]);
    };
    const handleDashboardUpdate = (event: MessageEvent) => {
      try {
        const payload = JSON.parse(event.data) as { reason?: string | null };
        if (payload.reason === "account_limit") {
          invalidateQueries(["snapshot", "account-limits", "alerts"]);
          return;
        }
      } catch {
        // Fall back to the safe broad refresh if the event payload is malformed.
      }
      invalidateDashboardData();
    };
    const handleOpen = () => {
      if (!eventSourceHadErrorRef.current) return;
      eventSourceHadErrorRef.current = false;
      invalidateDashboardData();
    };
    const handleError = () => {
      eventSourceHadErrorRef.current = true;
    };
    events.addEventListener("open", handleOpen);
    events.addEventListener("error", handleError);
    events.addEventListener("dashboard_update", handleDashboardUpdate);
    return () => {
      events.removeEventListener("open", handleOpen);
      events.removeEventListener("error", handleError);
      events.removeEventListener("dashboard_update", handleDashboardUpdate);
      events.close();
    };
  }, [queryClient]);

  const selectedTotals = useMemo(() => rangeTotals(days.data?.days || []), [days.data]);
  const groupedRows = useMemo(() => groupedUsageRowsForReport(days.data, groupMode), [days.data, groupMode]);
  const updateTone = updateStatus.data?.state === "update_available" ? "warn" : updateStatus.data?.state === "updating" ? "loading" : "ok";
  const updateLabel = updateStatus.data?.state === "update_available"
    ? `Update v${updateStatus.data.latest_version}`
    : updateStatus.data?.state === "updating"
      ? "Updating"
      : updateStatus.data?.state === "up_to_date"
        ? "Current"
        : null;
  const activeTabLabel = navItems.find((item) => item.id === activeTab)?.label || "Dashboard";
  const scopedAccountLabel = effectiveAccounts.length
    ? `${effectiveAccounts.length} account${effectiveAccounts.length === 1 ? "" : "s"}`
    : singleKnownAccount
      ? singleKnownAccount.account
      : "All accounts";
  const showMemoryCacheWarning = usesMemoryCache(snapshot.data?.cache) && !memoryCacheWarningDismissed;
  const memoryCacheDetail = cacheBackendLabel(snapshot.data?.cache);

  function applyRange(next: DateRange, options?: { preset?: Preset }) {
    const nextChartMode = options?.preset === "today" ? "bar" : chartMode;
    setRange(next);
    setDraftRange(next);
    setChartMode(nextChartMode);
    setRangeMode("datetime");
    writeDashboardStateToUrl(next, groupMode, nextChartMode, selectedAccounts, activeTab);
  }

  function applyGroupMode(next: GroupMode) {
    setGroupMode(next);
    writeDashboardStateToUrl(range, next, chartMode, selectedAccounts, activeTab);
  }

  function applyChartMode(next: ChartMode) {
    setChartMode(next);
    writeDashboardStateToUrl(range, groupMode, next, selectedAccounts, activeTab);
  }

  function applyAccounts(next: string[]) {
    setSelectedAccounts(next);
    writeDashboardStateToUrl(range, groupMode, chartMode, next, activeTab);
  }

  function applyTab(next: AppTab) {
    setActiveTab(next);
    writeTabToUrl(next);
  }

  async function refreshAll() {
    await queryClient.invalidateQueries();
  }

  return (
    <div className="min-h-screen">
      {reloadNotice ? (
        <div className="fixed inset-x-0 top-0 z-50 border-b border-border bg-panel px-4 py-3 shadow-lg">
          <div className="mx-auto flex max-w-[100rem] flex-wrap items-center justify-between gap-3">
            <div className="flex min-w-0 items-center gap-2 text-sm text-ink">
              <TriangleAlert className="h-4 w-4 shrink-0 text-accent" />
              <span className="break-words">{reloadNotice}</span>
            </div>
            <button
              type="button"
              onClick={() => window.location.reload()}
              className="inline-flex items-center gap-2 rounded-md border border-border bg-brand px-3 py-2 text-sm font-semibold text-white dark:text-slate-950"
            >
              <RefreshCw className="h-4 w-4" />
              Reload
            </button>
          </div>
        </div>
      ) : null}
      {dataOverlayVisible ? <DataLoadingOverlay label={dashboardSnapshotBusy ? "Waiting for snapshot" : dashboardDataBusy ? "Updating charts" : "Updating sessions"} /> : null}
      <div className="min-h-screen">
        <header className="sticky top-0 z-20 border-b border-border bg-panel/95 shadow-sm shadow-black/5 backdrop-blur">
          <div className="mx-auto max-w-[112rem] px-3 py-2.5 sm:px-4 lg:px-6">
            <div className="flex flex-wrap items-center gap-3">
              <div className="flex min-w-[14rem] shrink-0 items-center gap-3">
                <img
                  src="/static/favicon.svg"
                  alt=""
                  className="h-9 w-9 shrink-0 rounded-lg shadow-sm"
                  aria-hidden="true"
                />
                <div className="min-w-0">
                  <div className="truncate text-sm font-bold tracking-normal">Codex Self-Hosted Web Monitor</div>
                  {snapshot.data?.version ? <div className="text-xs font-semibold text-muted">v{snapshot.data.version}</div> : null}
                </div>
              </div>
              <nav className="flex min-w-0 flex-1 gap-1 overflow-x-auto rounded-sm border border-border/70 bg-canvas/65 p-1" aria-label="Workspace">
                {navItems.map((item) => (
                  <button
                    key={item.id}
                    type="button"
                    className={`inline-flex min-w-fit items-center gap-2 rounded-[3px] px-3 py-2 text-sm font-semibold ${activeTab === item.id ? "bg-brand text-white shadow-sm dark:text-slate-950" : "text-muted hover:bg-panel hover:text-ink"}`}
                    onClick={() => applyTab(item.id)}
                  >
                    {item.icon}
                    {item.label}
                  </button>
                ))}
              </nav>
              <div className="flex min-w-0 flex-wrap items-center gap-2 sm:justify-end">
                <QueryStateBar loading={isLoading} fetching={isFetching} error={firstError as Error | null} />
                {updateLabel ? <StatusPill tone={updateTone}>{updateLabel}</StatusPill> : null}
                <button
                  type="button"
                  onClick={() => setShowChangelog(true)}
                  className="inline-flex items-center gap-2 rounded-sm border border-border bg-panel px-3 py-2 text-sm font-semibold"
                >
                  <ScrollText className="h-4 w-4" />
                  What's new
                </button>
                <button
                  type="button"
                  onClick={refreshAll}
                  className="inline-flex items-center gap-2 rounded-sm border border-border bg-panel px-3 py-2 text-sm font-semibold"
                >
                  <RefreshCw className={`h-4 w-4 ${isFetching ? "animate-spin" : ""}`} />
                  Refresh
                </button>
              </div>
            </div>
            <div className="mt-3 flex flex-wrap items-center gap-x-4 gap-y-1 border-t border-border/70 pt-2 text-xs font-semibold text-muted">
              <span className="text-ink">{activeTabLabel}</span>
              <span className="inline-flex items-center gap-1.5">
                <Clock3 className="h-3.5 w-3.5" />
                {formatDateTime(snapshot.data?.generated_at)}
              </span>
              <span>Range {formatRangeBound(range.start_at)} to {formatRangeBound(range.end_at)}</span>
              <span className="min-w-0 break-all">{scopedAccountLabel}</span>
            </div>
          </div>
        </header>

        <div className="min-w-0">
          <main className="workspace-content mx-auto grid max-w-[112rem] gap-3 px-3 pb-3 pt-3 sm:gap-4 sm:px-4 sm:pb-4 sm:pt-4 lg:px-6">
            {showChangelog ? (
              <ChangelogDialog
                changelog={changelog.data}
                error={changelog.error as Error | null}
                loading={changelog.isLoading}
                onClose={() => setShowChangelog(false)}
              />
            ) : null}

            {firstError ? <ErrorBlock message={(firstError as Error).message} /> : null}
            {showMemoryCacheWarning ? (
              <div className="rounded-md border border-accent/45 bg-accent/10 px-4 py-3 text-sm text-ink shadow-sm">
                <div className="flex items-start justify-between gap-3">
                  <div className="flex min-w-0 items-start gap-3">
                    <TriangleAlert className="mt-0.5 h-4 w-4 shrink-0 text-accent" />
                    <div className="min-w-0">
                      <div className="font-semibold">Response cache is using in-memory fallback.</div>
                      <div className="mt-1 break-words text-muted">
                        Valkey or Redis is not reachable, so reports still work but the cache is not shared or persistent. Current backend: {memoryCacheDetail}.
                      </div>
                    </div>
                  </div>
                  <button
                    type="button"
                    onClick={() => setMemoryCacheWarningDismissed(true)}
                    className="inline-flex h-8 w-8 shrink-0 items-center justify-center rounded-md border border-accent/30 bg-panel/70 text-accent"
                    aria-label="Dismiss memory cache warning"
                  >
                    <X className="h-4 w-4" />
                  </button>
                </div>
              </div>
            ) : null}

            {activeTab === "settings" ? (
              <SettingsTab
                accounts={accounts.data}
                accountLimits={accountLimits.data}
                rateCardRows={rateCard.data?.rows}
                settings={settings.data}
                settingsLoading={settings.isLoading}
              />
            ) : activeTab === "sessions" ? (
              <SessionsTab
                accounts={accounts.data}
                accountsLoading={accounts.isLoading}
                applyAccounts={applyAccounts}
                applyRange={applyRange}
                draftRange={draftRange}
                focusedMode={Boolean(focusedMode)}
                range={range}
                rangeError={rangeError}
                selectedAccounts={effectiveAccounts}
                setDraftRange={setDraftRange}
                sessions={sessions.data}
                diagnostics={diagnostics.data}
                diagnosticsError={diagnostics.isError}
                diagnosticsFetching={diagnostics.isFetching}
                sessionsFetching={sessions.isFetching}
                sessionsLoading={sessionsLoading}
                signalThresholds={signalThresholds}
                timezone={timezone}
              />
            ) : (
              <DashboardTab
                accounts={accounts.data}
                accountsLoading={accounts.isLoading}
                alerts={alerts.data}
                alertsFetching={alerts.isFetching}
                alertsLoading={alerts.isLoading}
                accountLimitStatuses={accountLimits.data?.statuses || snapshot.data?.account_limits || []}
                applyAccounts={applyAccounts}
                applyChartMode={applyChartMode}
                applyGroupMode={applyGroupMode}
                applyRange={applyRange}
                chartMode={chartMode}
                days={days.data}
                daysFetching={days.isFetching}
                daysLoading={days.isLoading}
                draftRange={draftRange}
                focusedMode={Boolean(focusedMode)}
                groupMode={groupMode}
                groupedRows={groupedRows}
                range={range}
                rangeError={rangeError}
                selectedAccounts={selectedAccounts}
                selectedTotals={selectedTotals}
                setDraftRange={setDraftRange}
                sessions={sessions.data}
                sessionsFetching={sessions.isFetching}
                sessionsPlaceholder={sessions.isPlaceholderData}
                signalThresholds={signalThresholds}
                updateStatus={updateStatus.data}
                onOpenSettings={() => applyTab("settings")}
                snapshot={snapshot.data}
                snapshotLoading={snapshot.isLoading}
                summary={summary.data}
                summaryFetching={summary.isFetching}
                summaryLoading={summary.isLoading}
                timezone={timezone}
              />
            )}
          </main>
        </div>
      </div>
    </div>
  );
}
