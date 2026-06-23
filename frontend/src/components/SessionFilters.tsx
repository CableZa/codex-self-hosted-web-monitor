import { useState, type Dispatch, type SetStateAction } from "react";
import { AlertTriangle, Database, Filter, Search, X } from "lucide-react";
import type { AccountsReport, DateRange } from "../lib/apiTypes";
import type { SessionWasteReasonId } from "../lib/dashboardSignals";
import { sessionWasteReasonOptions } from "../lib/dashboardSignals";
import type { SessionSignalThresholds } from "../lib/sessionSignalThresholds";
import type { Preset } from "../lib/dateRange";
import { Spinner } from "./Spinner";
import { SignalInfoButton, SignalInfoDialog } from "./SessionSignalInfo";
import { UsageWindowControls } from "./UsageWindowControls";

export function FilterControls({
  accounts,
  accountsLoading,
  applyAccounts,
  applyRange,
  draftRange,
  focusedMode,
  rangeError,
  singleAccountLabel,
  selectedAccounts,
  setDraftRange,
  timezone,
}: {
  accounts?: AccountsReport;
  accountsLoading: boolean;
  applyAccounts: (accounts: string[]) => void;
  applyRange: (range: DateRange, options?: { preset?: Preset }) => void;
  draftRange: DateRange;
  focusedMode: boolean;
  rangeError: string;
  singleAccountLabel?: string;
  selectedAccounts: string[];
  setDraftRange: Dispatch<SetStateAction<DateRange>>;
  timezone: string;
}) {
  return (
    <div className="mb-4 grid gap-3">
      <UsageWindowControls
        applyRange={applyRange}
        draftRange={draftRange}
        rangeError={rangeError}
        setDraftRange={setDraftRange}
        timezone={timezone}
      />
      {singleAccountLabel ? (
        <div className="inline-flex w-fit items-center gap-2 rounded-md border border-border bg-canvas/60 px-3 py-2 text-sm">
          <span className="text-muted">Account</span>
          <span className="font-semibold text-ink">{singleAccountLabel}</span>
        </div>
      ) : null}
      {!focusedMode && !singleAccountLabel ? (
        <div className="rounded-lg border border-border bg-canvas/60 p-3">
          <div className="mb-2 flex flex-wrap items-center justify-between gap-2">
            <div className="inline-flex items-center gap-2 text-sm font-semibold">
              <Filter className="h-4 w-4 text-brand" />
              Accounts
            </div>
            <button
              type="button"
              className="text-sm font-semibold text-brand disabled:text-muted"
              disabled={!selectedAccounts.length}
              onClick={() => applyAccounts([])}
            >
              Show all
            </button>
          </div>
          {accountsLoading ? (
            <Spinner label="Loading accounts" />
          ) : accounts?.accounts.length ? (
            <div className="flex flex-wrap gap-2">
              {accounts.accounts.map((option) => {
                const active = selectedAccounts.length === 0 || selectedAccounts.includes(option.account);
                const nextAccounts = selectedAccounts.includes(option.account)
                  ? selectedAccounts.filter((account) => account !== option.account)
                  : [...selectedAccounts, option.account];
                return (
                  <button
                    key={option.account}
                    type="button"
                    className={`max-w-full rounded-md border px-3 py-2 text-left text-sm font-semibold sm:max-w-[22rem] ${active ? "border-brand bg-brand text-white dark:text-slate-950" : "border-border bg-panel text-muted"}`}
                    title={`${option.first_seen || "unknown"} to ${option.last_seen || "unknown"}`}
                    onClick={() => applyAccounts(nextAccounts)}
                  >
                    <span className="break-anywhere">{option.account}</span>
                  </button>
                );
              })}
            </div>
          ) : (
            <div className="text-sm text-muted">No account snapshots yet. The service will record one on the next monitor tick.</div>
          )}
        </div>
      ) : null}
    </div>
  );
}

function SelectFilter({
  label,
  value,
  values,
  onChange,
}: {
  label: string;
  value: string;
  values: string[];
  onChange: (value: string) => void;
}) {
  return (
    <label className="grid gap-1 text-sm text-muted">
      {label}
      <select className="rounded-sm border border-border bg-canvas px-3 py-2 text-ink" value={value} onChange={(event) => onChange(event.target.value)}>
        <option value="">All</option>
        {values.map((item) => (
          <option key={item} value={item}>{item}</option>
        ))}
      </select>
    </label>
  );
}

export function SessionAnalyticsControls({
  accountFilter,
  accounts,
  longContextOnly,
  modelFilter,
  models,
  projectFilter,
  projects,
  search,
  setAccountFilter,
  setLongContextOnly,
  setModelFilter,
  setProjectFilter,
  setSearch,
  setSortMode,
  setUncachedHeavyOnly,
  setWasteReasonFilter,
  signalThresholds,
  showAccountFilter,
  sortMode,
  uncachedHeavyOnly,
  wasteReasonFilter,
}: {
  accountFilter: string;
  accounts: string[];
  longContextOnly: boolean;
  modelFilter: string;
  models: string[];
  projectFilter: string;
  projects: string[];
  search: string;
  setAccountFilter: (value: string) => void;
  setLongContextOnly: (value: boolean) => void;
  setModelFilter: (value: string) => void;
  setProjectFilter: (value: string) => void;
  setSearch: (value: string) => void;
  setSortMode: (value: string) => void;
  setUncachedHeavyOnly: (value: boolean) => void;
  setWasteReasonFilter: (value: SessionWasteReasonId | "") => void;
  signalThresholds: SessionSignalThresholds;
  showAccountFilter: boolean;
  sortMode: string;
  uncachedHeavyOnly: boolean;
  wasteReasonFilter: SessionWasteReasonId | "";
}) {
  const [showSignalInfo, setShowSignalInfo] = useState(false);
  const activeFilters = [
    search ? { key: "search", label: `Search: ${search}` } : null,
    sortMode !== "recent" ? { key: "sort", label: `Rank: ${sortMode}` } : null,
    modelFilter ? { key: "model", label: `Model: ${modelFilter}` } : null,
    projectFilter ? { key: "project", label: `Project: ${projectFilter}` } : null,
    showAccountFilter && accountFilter ? { key: "account", label: `Account: ${accountFilter}` } : null,
    wasteReasonFilter ? {
      key: "waste",
      label: `Waste: ${sessionWasteReasonOptions.find((reason) => reason.id === wasteReasonFilter)?.label || wasteReasonFilter}`,
    } : null,
    longContextOnly ? { key: "long-context", label: "Long context" } : null,
    uncachedHeavyOnly ? { key: "low-cache", label: "Low cache reuse" } : null,
  ].filter(Boolean) as Array<{ key: string; label: string }>;
  const hasActiveFilters = activeFilters.length > 0;

  function clearFilters() {
    setSearch("");
    setSortMode("recent");
    setModelFilter("");
    setProjectFilter("");
    setAccountFilter("");
    setWasteReasonFilter("");
    setLongContextOnly(false);
    setUncachedHeavyOnly(false);
  }

  return (
    <div className="grid gap-3 rounded-sm border border-border bg-canvas/60 p-3">
      {showSignalInfo ? <SignalInfoDialog onClose={() => setShowSignalInfo(false)} thresholds={signalThresholds} /> : null}
      <div className="flex flex-wrap items-end justify-between gap-3">
        <label className="grid min-w-[18rem] flex-1 gap-1 text-sm text-muted">
          Search
          <span className="flex items-center gap-2 rounded-sm border border-border bg-canvas px-3 py-2">
            <Search className="h-4 w-4 text-muted" />
            <input
              className="min-w-0 flex-1 bg-transparent text-ink outline-none"
              value={search}
              onChange={(event) => setSearch(event.target.value)}
              placeholder={showAccountFilter ? "Prompt, session, account, model, or project" : "Prompt, session, model, or project"}
            />
          </span>
        </label>
        <button
          type="button"
          className="inline-flex items-center gap-2 rounded-sm border border-border bg-panel px-3 py-2 text-sm font-semibold text-muted disabled:opacity-50"
          disabled={!hasActiveFilters}
          onClick={clearFilters}
        >
          <X className="h-4 w-4" />
          Clear filters
        </button>
      </div>
      <div className="grid gap-3 md:grid-cols-4">
        <label className="grid gap-1 text-sm text-muted">
          Rank by
          <select className="rounded-sm border border-border bg-canvas px-3 py-2 text-ink" value={sortMode} onChange={(event) => setSortMode(event.target.value)}>
            <option value="credits">Credits</option>
            <option value="waste">Likely waste</option>
            <option value="tokens">Tokens</option>
            <option value="uncached">Uncached input</option>
            <option value="cache">Lowest cache reuse</option>
            <option value="duration">Duration</option>
            <option value="recent">Most recent</option>
            <option value="oldest">Oldest</option>
          </select>
        </label>
        <SelectFilter label="Model" value={modelFilter} values={models} onChange={setModelFilter} />
        <SelectFilter label="Project" value={projectFilter} values={projects} onChange={setProjectFilter} />
        {showAccountFilter ? <SelectFilter label="Account" value={accountFilter} values={accounts} onChange={setAccountFilter} /> : null}
        <label className="grid gap-1 text-sm text-muted">
          Waste reason
          <select className="rounded-sm border border-border bg-canvas px-3 py-2 text-ink" value={wasteReasonFilter} onChange={(event) => setWasteReasonFilter(event.target.value as SessionWasteReasonId | "")}>
            <option value="">All</option>
            {sessionWasteReasonOptions.map((reason) => (
              <option key={reason.id} value={reason.id}>{reason.label}</option>
            ))}
          </select>
        </label>
      </div>
      {hasActiveFilters ? (
        <div className="flex flex-wrap gap-2 border-t border-border/70 pt-3">
          {activeFilters.map((filter) => (
            <span key={filter.key} className="max-w-full truncate rounded-sm border border-brand/35 bg-brand/10 px-2.5 py-1 text-xs font-semibold text-brand">
              {filter.label}
            </span>
          ))}
        </div>
      ) : null}
      <div className="flex flex-wrap gap-2">
        <button
          type="button"
          className={`inline-flex items-center gap-2 rounded-sm border px-3 py-2 text-sm font-semibold ${longContextOnly ? "border-brand bg-brand text-white dark:text-slate-950" : "border-border bg-panel text-muted"}`}
          onClick={() => setLongContextOnly(!longContextOnly)}
        >
          <AlertTriangle className="h-4 w-4" />
          Long context only
        </button>
        <button
          type="button"
          className={`inline-flex items-center gap-2 rounded-sm border px-3 py-2 text-sm font-semibold ${uncachedHeavyOnly ? "border-brand bg-brand text-white dark:text-slate-950" : "border-border bg-panel text-muted"}`}
          onClick={() => setUncachedHeavyOnly(!uncachedHeavyOnly)}
        >
          <Database className="h-4 w-4" />
          Low cache reuse only
        </button>
        <SignalInfoButton open={() => setShowSignalInfo(true)} title="Explain session signals" />
      </div>
    </div>
  );
}
