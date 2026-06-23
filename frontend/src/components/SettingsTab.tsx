import { useEffect, useRef, useState } from "react";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { Check, Info, Palette, RefreshCw, RotateCcw, Send, Settings as SettingsIcon, SlidersHorizontal, WalletCards, X } from "lucide-react";
import { saveSettings, testWebhook } from "../lib/api";
import type { AccountLimitsReport, AccountsReport, RateCard, Settings } from "../lib/apiTypes";
import { confirmedAccounts } from "../lib/accountAttribution";
import { credits } from "../lib/format";
import { Panel } from "./Panel";
import { StatusPill } from "./StatusPill";
import { AccountLimitSettings } from "./AccountLimits";
import { AccountAttributionPanel } from "./AccountAttributionPanel";
import { LoaderBlock } from "./DashboardPrimitives";
import { isValidCreditInteger } from "../lib/creditInteger";
import { CreditIntegerInput } from "./CreditIntegerInput";
import { NumericInput } from "./NumericInput";
import { defaultSessionSignalThresholdSettings } from "../lib/sessionSignalThresholds";
import { SettingsSaveBar, SettingsSection, SettingsSectionNav } from "./SettingsLayout";

function editableSettingsPayload(form: Partial<Settings>) {
  const editable = { ...form };
  delete editable.webhook_ui_enabled;
  return editable;
}

function CreditEstimateNotes() {
  return (
    <details className="rounded-lg border border-border bg-canvas/50 p-4 text-sm text-muted open:bg-canvas/70">
      <summary className="cursor-pointer select-none font-semibold text-ink">
        <span className="inline-flex items-center gap-2">
          <Info className="h-4 w-4 text-brand" />
          How to read Codex credits
        </span>
      </summary>
      <div className="mt-3 space-y-3 leading-6">
        <p>
          The dashboard uses the OpenAI Codex rate card as the primary usage unit. It multiplies observed input, cached input,
          and output tokens by model credit rates per 1M tokens.
        </p>
        <p>
          This is useful for budgets, alerts, and comparing heavy days. It is not a billing statement, and it may not equal your real
          cost when Codex is authenticated through a ChatGPT subscription or Enterprise workspace.
        </p>
        <p>
          Fast mode can consume credits at a higher rate. The local session logs do not currently expose a reliable selected fast-mode field,
          so this app uses standard credit rates unless a future log format makes fast mode explicit.
        </p>
        <p>
          For ChatGPT Enterprise, treat credits as a usage-pressure estimate. Enterprise plans can include baseline access, flexible pricing,
          shared credit pools, and workspace controls, so token activity might count against credits, an included allowance, a contract limit,
          or no direct per-token bill at all. Your workspace contract and admin settings are the source of truth.
        </p>
      </div>
    </details>
  );
}

function RateCardPanel({ rows }: { rows?: RateCard["rows"] }) {
  if (!rows?.length) return null;
  const primaryModels = rows.filter((row) => ["gpt-5.5", "gpt-5.4", "gpt-5.4-mini", "gpt-5.3-codex", "gpt-5.2-codex"].includes(row.model));
  return (
    <details className="rounded-lg border border-border bg-canvas/50 p-4 text-sm text-muted open:bg-canvas/70">
      <summary className="cursor-pointer select-none font-semibold text-ink">
        <span className="inline-flex items-center gap-2">
          <WalletCards className="h-4 w-4 text-brand" />
          Codex credit rate card
        </span>
      </summary>
      <div className="mt-3 overflow-x-auto">
        <table className="w-full min-w-[520px] text-left text-sm">
          <thead className="text-xs uppercase text-muted">
            <tr>
              <th className="border-b border-border py-2 pr-3">Model</th>
              <th className="border-b border-border py-2 pr-3">Input</th>
              <th className="border-b border-border py-2 pr-3">Cached input</th>
              <th className="border-b border-border py-2 pr-3">Output</th>
            </tr>
          </thead>
          <tbody>
            {primaryModels.map((row) => (
              <tr key={row.model}>
                <td className="border-b border-border/70 py-2 pr-3 font-semibold text-ink">{row.model}</td>
                <td className="border-b border-border/70 py-2 pr-3">{credits(row.input_credits)}</td>
                <td className="border-b border-border/70 py-2 pr-3">{credits(row.cached_input_credits)}</td>
                <td className="border-b border-border/70 py-2 pr-3">{credits(row.output_credits)}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      <p className="mt-3 text-xs text-muted">Rates are credits per 1M tokens. Fast mode is shown as a caveat because local logs do not reliably record the selected service tier.</p>
    </details>
  );
}

function WebhookHelpDialog({ onClose }: { onClose: () => void }) {
  const dialogRef = useRef<HTMLDivElement>(null);
  const closeButtonRef = useRef<HTMLButtonElement>(null);

  useEffect(() => {
    const previousFocus = document.activeElement instanceof HTMLElement ? document.activeElement : null;
    const timer = window.setTimeout(() => closeButtonRef.current?.focus(), 0);
    const handleKeyDown = (event: KeyboardEvent) => {
      if (event.key === "Escape") {
        onClose();
        return;
      }
      if (event.key !== "Tab" || !dialogRef.current) return;
      const focusable = Array.from(
        dialogRef.current.querySelectorAll<HTMLElement>(
          'button:not([disabled]), input:not([disabled]), select:not([disabled]), [tabindex]:not([tabindex="-1"])',
        ),
      ).filter((element) => element.offsetParent !== null || element === closeButtonRef.current);
      if (!focusable.length) return;
      const first = focusable[0];
      const last = focusable[focusable.length - 1];
      const active = document.activeElement;
      const activeInside = active instanceof HTMLElement && dialogRef.current.contains(active);
      if (event.shiftKey && (!activeInside || active === first)) {
        event.preventDefault();
        last.focus();
      } else if (!event.shiftKey && (!activeInside || active === last)) {
        event.preventDefault();
        first.focus();
      }
    };
    window.addEventListener("keydown", handleKeyDown);
    return () => {
      window.clearTimeout(timer);
      window.removeEventListener("keydown", handleKeyDown);
      previousFocus?.focus();
    };
  }, [onClose]);

  return (
    <div className="fixed inset-0 z-40 flex items-center justify-center bg-black/60 p-4" role="presentation" onClick={onClose}>
      <div
        ref={dialogRef}
        className="max-h-[90vh] w-full max-w-2xl overflow-auto rounded-lg border border-border bg-panel p-5 shadow-xl"
        role="dialog"
        aria-modal="true"
        aria-labelledby="webhook-help-title"
        tabIndex={-1}
        onClick={(event) => event.stopPropagation()}
      >
        <div className="mb-4 flex items-start justify-between gap-3">
          <div>
            <h2 id="webhook-help-title" className="text-lg font-bold text-ink">Webhook URL</h2>
            <p className="mt-1 text-sm text-muted">An optional outbound HTTP endpoint for alerts and summaries.</p>
          </div>
          <button
            ref={closeButtonRef}
            type="button"
            className="inline-flex h-8 w-8 items-center justify-center rounded-md border border-border bg-canvas text-muted hover:border-brand hover:text-brand"
            onClick={onClose}
          >
            <X className="h-4 w-4" />
            <span className="sr-only">Close</span>
          </button>
        </div>
        <div className="grid gap-3 text-sm text-muted">
          <div className="rounded-md border border-border bg-canvas/60 p-3">
            <div className="font-semibold text-ink">What it does</div>
            <p className="mt-1">When set, the monitor sends JSON payloads to this URL for account limit alerts, burn alerts, scheduled usage summaries, and the Test webhook button.</p>
          </div>
          <div className="rounded-md border border-border bg-canvas/60 p-3">
            <div className="font-semibold text-ink">Common destinations</div>
            <p className="mt-1">Use an HTTPS endpoint from a Slack, Teams, Discord, ntfy, Gotify, Pushover, Zapier, Make, Home Assistant, or custom relay.</p>
          </div>
          <div className="rounded-md border border-border bg-canvas/60 p-3">
            <div className="font-semibold text-ink">Privacy and safety</div>
            <p className="mt-1">Leave it blank to send nothing. The monitor validates that webhook targets use HTTP or HTTPS and blocks local or unsafe outbound URLs.</p>
          </div>
        </div>
      </div>
    </div>
  );
}

function WebhookUrlInput({
  onChange,
  onHelp,
  value,
}: {
  onChange: (value: string) => void;
  onHelp: () => void;
  value: string;
}) {
  return (
    <div className="grid gap-1.5 text-sm text-muted">
      <div className="flex items-center gap-2">
        <label htmlFor="webhook-url">Webhook URL</label>
        <button
          type="button"
          className="inline-flex h-7 w-7 items-center justify-center rounded-md border border-border bg-panel text-muted hover:border-brand hover:text-brand"
          onClick={onHelp}
          title="Explain webhook URL"
        >
          <Info className="h-4 w-4" />
          <span className="sr-only">Explain webhook URL</span>
        </button>
      </div>
      <input
        id="webhook-url"
        className="rounded-md border border-border bg-canvas px-3 py-2 text-ink"
        inputMode="url"
        placeholder="https://example.com/webhook"
        value={value}
        onChange={(event) => onChange(event.target.value)}
      />
      <span className="text-xs text-muted">Optional. Sends alert and summary JSON to your chosen HTTP endpoint.</span>
    </div>
  );
}

function UnknownAccountMappingInput({
  accounts,
  onChange,
  value,
}: {
  accounts?: AccountsReport;
  onChange: (value: string) => void;
  value: string;
}) {
  const knownAccounts = confirmedAccounts(accounts);
  return (
    <label className="grid gap-1.5 text-sm text-muted">
      Assign unknown usage
      <select
        className="rounded-md border border-border bg-canvas px-3 py-2 text-ink disabled:opacity-60"
        disabled={!knownAccounts.length}
        value={value}
        onChange={(event) => onChange(event.target.value)}
      >
        <option value="">Keep as unknown</option>
        {knownAccounts.map((option) => (
          <option key={option.account} value={option.account}>{option.account}</option>
        ))}
      </select>
      <span className="text-xs text-muted">Applies to usage before the first matching auth snapshot.</span>
    </label>
  );
}

const sessionTokenThresholdKeys: Array<{ key: keyof Settings; label: string }> = [
  { key: "session_high_input_tokens", label: "High input volume tokens" },
  { key: "session_high_uncached_input_tokens", label: "High uncached input tokens" },
  { key: "session_low_cache_min_uncached_tokens", label: "Low-cache minimum uncached tokens" },
  { key: "session_large_total_tokens", label: "Large token footprint tokens" },
  { key: "session_high_output_tokens", label: "High output volume tokens" },
];

function ratioIsValid(value: string) {
  if (!value.trim()) return false;
  const number = Number(value);
  return Number.isFinite(number) && number >= 0 && number <= 1;
}

function thresholdSettingValue(form: Partial<Settings>, key: keyof typeof defaultSessionSignalThresholdSettings) {
  return String(form[key] ?? defaultSessionSignalThresholdSettings[key]);
}

function SessionSignalThresholdSettings({
  form,
  valid,
  onChange,
  onReset,
}: {
  form: Partial<Settings>;
  valid: boolean;
  onChange: (key: keyof Settings, value: string) => void;
  onReset: () => void;
}) {
  const longContextEnabled = String(form.session_long_context_pricing_signal_enabled ?? defaultSessionSignalThresholdSettings.session_long_context_pricing_signal_enabled).toLowerCase() !== "false";
  return (
    <div className="rounded-sm border border-border bg-panel/65 p-4">
      <div className="mb-3 flex flex-wrap items-start justify-between gap-3">
        <div>
          <div className="inline-flex items-center gap-2 text-sm font-semibold text-ink">
            <SlidersHorizontal className="h-4 w-4 text-brand" />
            Session signal thresholds
          </div>
          <p className="mt-1 max-w-3xl text-sm text-muted">
            Triage thresholds for Sessions signals and likely-waste ranking. Alerts and account caps stay separate.
          </p>
        </div>
        <button
          type="button"
          className="inline-flex items-center gap-2 rounded-sm border border-border bg-panel px-3 py-2 text-sm font-semibold text-muted hover:border-brand hover:text-brand"
          onClick={onReset}
        >
          <RotateCcw className="h-4 w-4" />
          Reset defaults
        </button>
      </div>
      <div className="grid gap-3 md:grid-cols-2 xl:grid-cols-3">
        {sessionTokenThresholdKeys.map((item) => (
          <CreditIntegerInput
            key={item.key}
            label={item.label}
            value={thresholdSettingValue(form, item.key as keyof typeof defaultSessionSignalThresholdSettings)}
            onChange={(value) => onChange(item.key, value)}
          />
        ))}
        <NumericInput
          label="Low-cache max cache reuse ratio"
          min={0}
          step="0.05"
          value={thresholdSettingValue(form, "session_low_cache_max_reuse_ratio")}
          onChange={(value) => onChange("session_low_cache_max_reuse_ratio", value)}
        />
        <label className="grid gap-1.5 text-sm text-muted">
          Long-context pricing signal
          <button
            type="button"
            className={`inline-flex h-10 items-center justify-between gap-3 rounded-sm border px-3 py-2 text-sm font-semibold ${longContextEnabled ? "border-brand bg-brand text-white dark:text-slate-950" : "border-border bg-panel text-muted"}`}
            onClick={() => onChange("session_long_context_pricing_signal_enabled", longContextEnabled ? "false" : "true")}
            aria-pressed={longContextEnabled}
          >
            <span>{longContextEnabled ? "Visible" : "Hidden"}</span>
            <span className={`h-2.5 w-2.5 rounded-full ${longContextEnabled ? "bg-white dark:bg-slate-950" : "bg-muted"}`} />
          </button>
        </label>
      </div>
      {!valid ? (
        <div className="mt-3 rounded-md border border-danger/35 bg-danger/10 p-3 text-sm text-danger">
          Session signal token thresholds must be positive whole numbers. Low-cache reuse ratio must be between 0 and 1.
        </div>
      ) : null}
    </div>
  );
}

function ThemeSelector({ onChange, value }: { onChange: (value: string) => void; value: string }) {
  const selected = value === "classic" ? "classic" : "catppuccin";
  const options = [
    {
      id: "catppuccin",
      label: "Purple tint",
      swatches: ["rgb(203 166 247)", "rgb(245 194 231)", "rgb(28 24 36)"],
    },
    {
      id: "classic",
      label: "Classic green",
      swatches: ["rgb(4 120 87)", "rgb(234 88 12)", "rgb(236 239 233)"],
    },
  ];
  return (
    <div className="grid gap-3 sm:grid-cols-2">
      {options.map((option) => (
        <button
          key={option.id}
          type="button"
          className={`rounded-sm border p-3 text-left transition ${selected === option.id ? "border-brand bg-brand/10 text-ink" : "border-border bg-panel/70 text-muted hover:border-brand hover:text-ink"}`}
          onClick={() => onChange(option.id)}
          aria-pressed={selected === option.id}
        >
          <span className="flex items-center justify-between gap-3">
            <span className="inline-flex items-center gap-2 text-sm font-semibold">
              <Palette className="h-4 w-4 text-brand" />
              {option.label}
            </span>
            <span className="inline-flex gap-1" aria-hidden="true">
              {option.swatches.map((swatch) => (
                <span key={swatch} className="h-4 w-4 rounded-full border border-border" style={{ background: swatch }} />
              ))}
            </span>
          </span>
        </button>
      ))}
    </div>
  );
}

function stableSettingsJson(settings?: Partial<Settings>) {
  return JSON.stringify(editableSettingsPayload(settings || {}), Object.keys(editableSettingsPayload(settings || {})).sort());
}

function SettingsForm({
  accounts,
  accountLimits,
  initial,
  rateCardRows,
}: {
  accounts?: AccountsReport;
  accountLimits?: AccountLimitsReport;
  initial?: Settings;
  rateCardRows?: RateCard["rows"];
}) {
  const queryClient = useQueryClient();
  const [form, setForm] = useState<Partial<Settings>>({});
  const [showWebhookHelp, setShowWebhookHelp] = useState(false);
  const saveMutation = useMutation({
    mutationFn: (settings: Partial<Settings>) => saveSettings(editableSettingsPayload(settings)),
    onSuccess: async () => {
      await Promise.all([
        queryClient.invalidateQueries({ queryKey: ["settings"] }),
        queryClient.invalidateQueries({ queryKey: ["snapshot"] }),
        queryClient.invalidateQueries({ queryKey: ["accounts"] }),
        queryClient.invalidateQueries({ queryKey: ["days"] }),
        queryClient.invalidateQueries({ queryKey: ["summary"] }),
        queryClient.invalidateQueries({ queryKey: ["sessions"] }),
        queryClient.invalidateQueries({ queryKey: ["session-detail"] }),
      ]);
    },
  });
  const webhookMutation = useMutation({ mutationFn: testWebhook });

  useEffect(() => {
    if (initial) {
      setForm(initial);
    }
  }, [initial]);

  function update(key: keyof Settings, value: string) {
    setForm((current) => ({ ...current, [key]: value }));
  }

  const pricingMode = (form.pricing_mode || "credits").trim().toLowerCase();
  const usesCreditPricing = pricingMode === "credits";
  const dashboardMode = (form.dashboard_mode || "full").trim().toLowerCase();
  const dashboardModeOptions = ["full", "focused", "compact"];
  const showDashboardMode = dashboardModeOptions.includes(dashboardMode);
  const showWebhookControls = ["1", "true", "yes", "on"].includes(String(form.webhook_ui_enabled || initial?.webhook_ui_enabled || "").trim().toLowerCase())
    || Boolean(String(form.webhook_url || "").trim());
  const sessionThresholdsValid = sessionTokenThresholdKeys.every((item) => isValidCreditInteger(thresholdSettingValue(form, item.key as keyof typeof defaultSessionSignalThresholdSettings)))
    && ratioIsValid(thresholdSettingValue(form, "session_low_cache_max_reuse_ratio"));
  const dirty = stableSettingsJson(form) !== stableSettingsJson(initial);

  function settingInput(key: keyof Settings, label: string, inputMode: "decimal" | "text" | "url" = "text") {
    if (inputMode === "decimal") {
      return (
        <NumericInput
          key={key}
          label={label}
          value={String(form[key] || "")}
          onChange={(value) => update(key, value)}
        />
      );
    }
    return (
      <label key={key} className="grid gap-1.5 text-sm text-muted">
        {label}
        <input
          className="rounded-md border border-border bg-canvas px-3 py-2 text-ink"
          inputMode={inputMode}
          value={form[key] || ""}
          onChange={(event) => update(key, event.target.value)}
        />
      </label>
    );
  }

  return (
    <div className="space-y-4">
      {showWebhookControls && showWebhookHelp ? <WebhookHelpDialog onClose={() => setShowWebhookHelp(false)} /> : null}
      <SettingsSectionNav />
      <SettingsSection id="usage" kicker="Usage" title="Pricing and dashboard behavior">
        <div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-3">
          <div className="grid gap-1.5 text-sm text-muted">
            Pricing mode
            <div className="rounded-sm border border-border bg-canvas px-3 py-2">
              <div className="font-semibold capitalize text-ink">{pricingMode || "credits"}</div>
              <div className="mt-1 text-xs text-muted">Read-only in the dashboard</div>
            </div>
          </div>
          {!usesCreditPricing ? (
            <>
              {settingInput("daily_budget_zar", "Daily budget ZAR", "decimal")}
              {settingInput("weekly_budget_zar", "Weekly budget ZAR", "decimal")}
              {settingInput("monthly_budget_zar", "Monthly budget ZAR", "decimal")}
              {settingInput("usd_zar_fallback_rate", "Fallback USD/ZAR", "decimal")}
            </>
          ) : null}
          {showDashboardMode ? (
            <label className="grid gap-1.5 text-sm text-muted">
              Dashboard mode
              <select
                className="rounded-sm border border-border bg-canvas px-3 py-2 text-ink"
                value={dashboardMode}
                onChange={(event) => update("dashboard_mode", event.target.value)}
              >
                {dashboardModeOptions.includes(dashboardMode) ? null : <option value={dashboardMode}>{dashboardMode}</option>}
                {dashboardModeOptions.map((mode) => (
                  <option key={mode} value={mode}>{mode}</option>
                ))}
              </select>
            </label>
          ) : null}
        </div>
        <CreditEstimateNotes />
        <RateCardPanel rows={rateCardRows} />
      </SettingsSection>

      <SettingsSection id="appearance" kicker="Appearance" title="Interface theme">
        <ThemeSelector
          value={String(form.ui_theme || "catppuccin")}
          onChange={(value) => update("ui_theme", value)}
        />
      </SettingsSection>

      <SettingsSection id="accounts" kicker="Accounts" title="Attribution and unknown usage">
        <AccountAttributionPanel accounts={accounts} />
        <UnknownAccountMappingInput
          accounts={accounts}
          value={String(form.unknown_account_mapping || "")}
          onChange={(value) => update("unknown_account_mapping", value)}
        />
      </SettingsSection>

      <SettingsSection id="limits" kicker="Limits" title="Account runway and weekly caps">
        <AccountLimitSettings accounts={accounts} report={accountLimits} />
      </SettingsSection>

      <SettingsSection id="sessions" kicker="Sessions" title="Signal thresholds">
        <SessionSignalThresholdSettings
          form={form}
          valid={sessionThresholdsValid}
          onChange={update}
          onReset={() => setForm((current) => ({ ...current, ...defaultSessionSignalThresholdSettings }))}
        />
      </SettingsSection>

      <SettingsSection id="integrations" kicker="Integrations" title="Outbound notifications">
        {showWebhookControls ? (
          <div className="grid gap-3 sm:grid-cols-[minmax(0,1fr)_auto]">
            <WebhookUrlInput
              value={String(form.webhook_url || "")}
              onChange={(value) => update("webhook_url", value)}
              onHelp={() => setShowWebhookHelp(true)}
            />
            <div className="flex items-end">
              <button
                type="button"
                className="inline-flex items-center gap-2 rounded-sm border border-border bg-panel px-3 py-2 text-sm font-semibold"
                disabled={webhookMutation.isPending}
                onClick={() => webhookMutation.mutate()}
              >
                {webhookMutation.isPending ? <RefreshCw className="h-4 w-4 animate-spin" /> : <Send className="h-4 w-4" />}
                Test webhook
              </button>
            </div>
          </div>
        ) : (
          <div className="rounded-sm border border-border bg-panel/70 p-3 text-sm text-muted">
            Webhook controls are hidden unless enabled in configuration or a webhook URL is already set.
          </div>
        )}
      </SettingsSection>

      <SettingsSaveBar
        dirty={dirty}
        pending={saveMutation.isPending}
        valid={sessionThresholdsValid}
        onReset={() => setForm(initial || {})}
        onSave={() => saveMutation.mutate(form)}
        status={(
          <>
            {saveMutation.isSuccess ? <StatusPill><Check className="h-3.5 w-3.5" /> Saved</StatusPill> : null}
            {saveMutation.isError ? <StatusPill tone="warn">Save failed</StatusPill> : null}
            {showWebhookControls && webhookMutation.isSuccess ? <StatusPill tone={webhookMutation.data.sent ? "ok" : "warn"}>{webhookMutation.data.sent ? "Webhook sent" : `Not sent: ${webhookMutation.data.reason}`}</StatusPill> : null}
          </>
        )}
      />
    </div>
  );
}

export function SettingsTab({
  accounts,
  accountLimits,
  rateCardRows,
  settings,
  settingsLoading,
}: {
  accounts?: AccountsReport;
  accountLimits?: AccountLimitsReport;
  rateCardRows?: RateCard["rows"];
  settings?: Settings;
  settingsLoading: boolean;
}) {
  return (
    <Panel title="Settings" meta={<SettingsIcon className="h-4 w-4 text-brand" />}>
      <div className="space-y-4">
        {settingsLoading ? (
          <LoaderBlock label="Loading settings" />
        ) : (
          <SettingsForm
            accounts={accounts}
            accountLimits={accountLimits}
            initial={settings}
            rateCardRows={rateCardRows}
          />
        )}
      </div>
    </Panel>
  );
}
