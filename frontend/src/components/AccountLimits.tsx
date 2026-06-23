import { useEffect, useState } from "react";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { Check, Info, RefreshCw, Save, ShieldAlert } from "lucide-react";
import type { AccountLimitStatus, AccountLimitsReport, AccountsReport, AutoAccountLimitDefaults } from "../lib/apiTypes";
import { saveAccountLimit } from "../lib/api";
import { confirmedAccounts, editableAccountLimit, unconfirmedAccountLimits } from "../lib/accountAttribution";
import { formatDateTime, formatLimitValue, pct } from "../lib/format";
import { cardIconClasses } from "../lib/ui";
import { StatusPill } from "./StatusPill";
import { isValidCreditInteger, normalizeCreditInteger } from "../lib/creditInteger";
import { CreditIntegerInput } from "./CreditIntegerInput";

const resetWeekdays = [
  { value: 0, label: "Monday" },
  { value: 1, label: "Tuesday" },
  { value: 2, label: "Wednesday" },
  { value: 3, label: "Thursday" },
  { value: 4, label: "Friday" },
  { value: 5, label: "Saturday" },
  { value: 6, label: "Sunday" },
];

const timezoneOptions = ["UTC", "America/New_York", "Europe/London", "Asia/Tokyo"];
const defaultLimitThresholds = [0.7, 0.85, 0.95, 1.0];

function isAutoLimitAccount(account?: string, defaults?: AutoAccountLimitDefaults) {
  const normalized = String(account || "").trim().toLowerCase();
  return Boolean(normalized) && Boolean(defaults?.email_suffixes?.some((suffix) => normalized.endsWith(suffix.toLowerCase())));
}

function defaultLimitForm(account?: string, defaults?: AutoAccountLimitDefaults) {
  const autoLimit = isAutoLimitAccount(account, defaults);
  return {
    cap_value: normalizeCreditInteger(autoLimit ? defaults?.cap_credits : 4500),
    reset_weekday: autoLimit ? defaults?.reset_weekday ?? 4 : 4,
    reset_time: autoLimit ? defaults?.reset_time || "00:00" : "00:00",
    timezone: autoLimit ? defaults?.timezone || "UTC" : "UTC",
    enabled: true,
  };
}

function defaultLimitSaveThresholds(account?: string, defaults?: AutoAccountLimitDefaults) {
  return isAutoLimitAccount(account, defaults) ? defaults?.thresholds || defaultLimitThresholds : defaultLimitThresholds;
}

function limitTone(status: AccountLimitStatus) {
  if (status.exceeded || status.ratio >= 0.95) return "border-danger/50 bg-danger/10 text-danger";
  if (status.ratio >= 0.85) return "border-accent/50 bg-accent/10 text-accent";
  if (status.ratio >= 0.7) return "border-brand/50 bg-brand/10 text-brand";
  return "border-border bg-panel text-ink";
}

function metricLabel(metric?: string) {
  return metric === "total_credits" ? "credits" : "tokens";
}

function resetWeekdayLabel(value?: number) {
  return resetWeekdays.find((day) => day.value === value)?.label || "Friday";
}

function latestConfirmedAccount(accounts?: AccountsReport) {
  return [...confirmedAccounts(accounts)].sort((left, right) => {
    return String(right.last_seen || "").localeCompare(String(left.last_seen || ""));
  })[0]?.account || "";
}

export function AccountLimitCard({ accountLabel, status }: { accountLabel?: string; status?: AccountLimitStatus }) {
  if (!status) {
    return (
      <div className="rounded-lg border border-border bg-panel p-4 shadow-sm">
        <div className="flex items-center gap-2 text-sm text-muted">
          <ShieldAlert className={cardIconClasses()} />
          <span>Account weekly limit</span>
        </div>
        <div className="mt-2 text-sm text-muted">
          {accountLabel ? `${accountLabel} does not have a weekly credit limit yet.` : "No active account limit configured."}
        </div>
      </div>
    );
  }
  const width = Math.min(100, Math.round(status.ratio * 100));
  const resetDay = resetWeekdayLabel(status.reset_weekday);
  return (
    <div className={`rounded-lg border p-4 shadow-sm ${limitTone(status)}`}>
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div>
          <div className="flex items-center gap-2 text-sm font-semibold">
            <ShieldAlert className="h-4 w-4" />
            <span>{status.account}</span>
          </div>
          <div className="mt-1 text-xs opacity-80">{resetDay} reset {new Date(status.reset_at).toLocaleString()}</div>
        </div>
        <div className="text-right">
          <div className="text-2xl font-bold tracking-normal">{pct(status.ratio)}</div>
          <div className="text-xs opacity-80">{status.exceeded ? "Exceeded" : "In progress"}</div>
        </div>
      </div>
      <div className="mt-4 h-3 overflow-hidden rounded-full bg-border/60">
        <div className={`h-full rounded-full ${status.exceeded ? "bg-danger" : "bg-brand"}`} style={{ width: `${width}%` }} />
      </div>
      <div className="mt-2 flex flex-wrap justify-between gap-2 text-xs opacity-90">
        <span>{formatLimitValue(status.current_value, status.metric)} / {formatLimitValue(status.cap_value, status.metric)}</span>
        <span>{formatLimitValue(status.remaining_value, status.metric)} remaining</span>
      </div>
    </div>
  );
}

export function AccountLimitSettings({ accounts, report }: { accounts?: AccountsReport; report?: AccountLimitsReport }) {
  const queryClient = useQueryClient();
  const confirmed = confirmedAccounts(accounts);
  const editableAccountNames = confirmed.map((option) => option.account);
  const unconfirmedLimits = unconfirmedAccountLimits(report, accounts);
  const confirmedLimitAccount = report?.limits.find((limit) => editableAccountNames.includes(limit.account))?.account || "";
  const fallbackAccount = confirmedLimitAccount || latestConfirmedAccount(accounts);
  const autoLimitDefaults = accounts?.auto_account_limit_defaults;
  const [selectedAccount, setSelectedAccount] = useState(fallbackAccount);
  const [form, setForm] = useState(defaultLimitForm(fallbackAccount, autoLimitDefaults));
  const mutation = useMutation({
    mutationFn: saveAccountLimit,
    onSuccess: (result) => {
      queryClient.setQueryData<AccountLimitsReport | undefined>(["account-limits"], (current) => {
        if (!current) return current;
        const limits = [...current.limits.filter((limit) => limit.account !== result.limit.account), result.limit]
          .sort((left, right) => left.account.localeCompare(right.account));
        const statuses = [
          ...current.statuses.filter((status) => status.account !== result.limit.account),
          ...(result.status ? [result.status] : []),
        ].sort((left, right) => left.account.localeCompare(right.account));
        return { limits, statuses, status_state: result.status_state || current.status_state };
      });
    },
  });
  const currentLimit = editableAccountLimit(report, selectedAccount);
  const currentStatus = report?.statuses.find((status) => status.account === selectedAccount);

  useEffect(() => {
    setSelectedAccount((current) => (editableAccountNames.includes(current) ? current : fallbackAccount));
  }, [editableAccountNames, fallbackAccount]);

  useEffect(() => {
    const defaults = defaultLimitForm(selectedAccount, autoLimitDefaults);
    setForm({
      cap_value: normalizeCreditInteger(currentLimit?.cap_value || defaults.cap_value),
      reset_weekday: currentLimit?.reset_weekday ?? currentStatus?.reset_weekday ?? defaults.reset_weekday,
      reset_time: currentLimit?.reset_time || currentStatus?.reset_time || defaults.reset_time,
      timezone: currentLimit?.timezone || currentStatus?.timezone || defaults.timezone,
      enabled: Boolean(currentLimit ? currentLimit.enabled : defaults.enabled),
    });
  }, [autoLimitDefaults, currentLimit, currentStatus, selectedAccount]);

  const canSave = Boolean(selectedAccount) && isValidCreditInteger(form.cap_value);
  const configuredStatuses = [...(report?.statuses || [])].sort((left, right) => {
    const ratioDelta = right.ratio - left.ratio;
    if (Math.abs(ratioDelta) > 0.0001) return ratioDelta;
    return left.account.localeCompare(right.account);
  });

  function saveLimit() {
    if (!canSave) return;
    mutation.mutate({
      account: selectedAccount.trim(),
      metric: "total_credits",
      cap_value: Number(form.cap_value),
      reset_weekday: form.reset_weekday,
      reset_time: form.reset_time,
      timezone: form.timezone,
      thresholds: defaultLimitSaveThresholds(selectedAccount, autoLimitDefaults),
      enabled: form.enabled,
    });
  }

  const selectedResetDay = resetWeekdayLabel(form.reset_weekday);
  const schedulePreview = `Every ${selectedResetDay} at ${form.reset_time} ${form.timezone}`;

  return (
    <div className="rounded-lg border border-border bg-canvas/50 p-4">
      <div className="mb-3 flex items-center gap-2 font-semibold">
        <ShieldAlert className="h-4 w-4 text-brand" />
        Account {metricLabel(currentStatus?.metric || currentLimit?.metric || "total_credits")} weekly limit
      </div>
      {unconfirmedLimits.length ? (
        <div className="mb-3 rounded-md border border-accent/40 bg-accent/10 px-3 py-2 text-sm text-accent">
          {unconfirmedLimits.length === 1
            ? `Stored limit for ${unconfirmedLimits[0].account} is read-only until a matching auth snapshot is recorded.`
            : `${unconfirmedLimits.length} stored limits are read-only until matching auth snapshots are recorded.`}
        </div>
      ) : null}
      <div className="grid gap-3 sm:grid-cols-[1fr_1fr_auto]">
        <label className="grid gap-1.5 text-sm text-muted">
          Confirmed account
          <select
            className="form-control rounded-md border border-border bg-canvas px-3 py-2 text-ink"
            disabled={!editableAccountNames.length}
            value={selectedAccount}
            onChange={(event) => setSelectedAccount(event.target.value)}
          >
            {!editableAccountNames.length ? <option value="">Auth snapshot required</option> : null}
            {confirmed.map((option) => (
              <option key={option.account} value={option.account}>{option.account}</option>
            ))}
          </select>
        </label>
        <CreditIntegerInput
          label="Weekly credit limit"
          value={form.cap_value}
          disabled={!editableAccountNames.length}
          onChange={(cap_value) => setForm((current) => ({ ...current, cap_value }))}
        />
        <label className="flex items-end gap-2 pb-2 text-sm font-semibold">
          <input
            type="checkbox"
            checked={form.enabled}
            disabled={!editableAccountNames.length}
            onChange={(event) => setForm((current) => ({ ...current, enabled: event.target.checked }))}
          />
          Enabled
        </label>
      </div>
      {!editableAccountNames.length ? (
        <div className="mt-2 rounded-md border border-accent/40 bg-accent/10 px-3 py-2 text-sm text-accent">
          Record a login or manual auth snapshot before configuring account caps.
        </div>
      ) : null}
      <fieldset className="mt-3 rounded-lg border border-border/70 p-3">
        <legend className="flex items-center gap-2 px-1 text-sm font-semibold text-ink">
          Limit window schedule
          <span title="The weekly limit window starts at this weekday and time in the selected timezone, then ends at the next reset.">
            <Info className="h-4 w-4 text-muted" />
          </span>
        </legend>
        <div className="grid gap-3 lg:grid-cols-[minmax(0,1.4fr)_minmax(0,1fr)]">
          <div className="rounded-md border border-border bg-canvas/60 p-3">
            <div className="text-xs font-semibold uppercase text-muted">Weekly reset</div>
            <div className="mt-2 grid gap-2 sm:grid-cols-[minmax(0,1fr)_8rem]">
              <label className="grid gap-1.5 text-sm text-muted">
                Day
                <select
                  className="form-control rounded-md border border-border bg-canvas px-3 py-2 text-ink"
                  disabled={!editableAccountNames.length}
                  value={form.reset_weekday}
                  onChange={(event) => setForm((current) => ({ ...current, reset_weekday: Number(event.target.value) }))}
                >
                  {resetWeekdays.map((day) => (
                    <option key={day.value} value={day.value}>{day.label}</option>
                  ))}
                </select>
              </label>
              <label className="grid gap-1.5 text-sm text-muted">
                At
                <input
                  className="rounded-md border border-border bg-canvas px-3 py-2 text-ink"
                  type="time"
                  disabled={!editableAccountNames.length}
                  value={form.reset_time}
                  onChange={(event) => setForm((current) => ({ ...current, reset_time: event.target.value }))}
                />
              </label>
            </div>
            <div className="mt-2 rounded-md border border-border/70 bg-panel/60 px-3 py-2 text-sm font-semibold text-ink">
              {schedulePreview}
            </div>
          </div>
          <label className="grid content-start gap-1.5 text-sm text-muted">
            Timezone
            <select
              className="form-control rounded-md border border-border bg-canvas px-3 py-2 text-ink"
              disabled={!editableAccountNames.length}
              value={form.timezone}
              onChange={(event) => setForm((current) => ({ ...current, timezone: event.target.value }))}
            >
              {timezoneOptions.includes(form.timezone) ? null : <option value={form.timezone}>{form.timezone}</option>}
              {timezoneOptions.map((timezone) => (
                <option key={timezone} value={timezone}>{timezone}</option>
              ))}
            </select>
          </label>
        </div>
      </fieldset>
      <dl className="mt-3 grid gap-x-4 gap-y-1 text-xs text-muted sm:grid-cols-[max-content_1fr]">
        <dt>Current window</dt>
        <dd>{currentStatus ? `${formatDateTime(currentStatus.window_start_at)} to ${formatDateTime(currentStatus.window_end_at)}` : "Not calculated yet"}</dd>
        <dt>Next reset</dt>
        <dd>{currentStatus ? formatDateTime(currentStatus.reset_at) : `Next ${selectedResetDay} at ${form.reset_time}`}</dd>
      </dl>
      {report?.status_state && report.status_state !== "ready" ? (
        <div className="mt-3 rounded-md border border-accent/40 bg-accent/10 px-3 py-2 text-sm text-accent">
          Usage status is refreshing. Saved limits are active while the latest usage window is recalculated.
        </div>
      ) : null}
      <div className="mt-3 flex flex-wrap items-center gap-3">
        <button
          type="button"
          className="inline-flex items-center gap-2 rounded-md border border-brand/40 bg-brand px-3 py-2 text-sm font-semibold text-white disabled:opacity-60 dark:text-slate-950"
          disabled={mutation.isPending || !canSave || !editableAccountNames.length}
          onClick={saveLimit}
        >
          {mutation.isPending ? <RefreshCw className="h-4 w-4 animate-spin" /> : <Save className="h-4 w-4" />}
          Save limit
        </button>
        {mutation.isSuccess ? <StatusPill><Check className="h-3.5 w-3.5" /> Saved</StatusPill> : null}
        {mutation.isError ? <StatusPill tone="warn">Save failed</StatusPill> : null}
      </div>
      <p className="mt-3 text-xs text-muted">
        This monitors Codex credits for the selected account in a {selectedResetDay}-reset week. It alerts at 70, 85, 95, and 100 percent and now drives focused runway and burn guidance.
      </p>
      {configuredStatuses.length ? (
        <div className="mt-4 rounded-lg border border-border/70 bg-panel/60 p-3">
          <div className="text-sm font-semibold text-ink">Configured accounts</div>
          <div className="mt-3 grid gap-2">
            {configuredStatuses.map((status) => (
              <div key={status.account} className="flex flex-wrap items-center justify-between gap-3 rounded-md border border-border/70 bg-canvas/70 px-3 py-2 text-sm">
                <div className="min-w-0">
                  <div className="break-anywhere font-semibold text-ink">{status.account}</div>
                  <div className="text-xs text-muted">Resets {formatDateTime(status.reset_at)}</div>
                </div>
                <div className="text-right">
                  <div className="font-semibold text-ink">{Math.round(status.ratio * 100)}%</div>
                  <div className="text-xs text-muted">{formatLimitValue(status.current_value, status.metric)} of {formatLimitValue(status.cap_value, status.metric)}</div>
                </div>
              </div>
            ))}
          </div>
        </div>
      ) : null}
    </div>
  );
}
