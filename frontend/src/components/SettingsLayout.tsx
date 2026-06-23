import type { ReactNode } from "react";
import { RefreshCw, RotateCcw, Save } from "lucide-react";
import { StatusPill } from "./StatusPill";

const settingsSections = [
  { id: "usage", label: "Usage" },
  { id: "appearance", label: "Appearance" },
  { id: "accounts", label: "Accounts" },
  { id: "limits", label: "Limits" },
  { id: "sessions", label: "Sessions" },
  { id: "integrations", label: "Integrations" },
] as const;

export function SettingsSectionNav() {
  return (
    <nav className="flex gap-1 overflow-x-auto rounded-sm border border-border bg-canvas/60 p-1" aria-label="Settings sections">
      {settingsSections.map((section) => (
        <a
          key={section.id}
          href={`#settings-${section.id}`}
          className="min-w-fit rounded-[3px] px-3 py-2 text-sm font-semibold text-muted hover:bg-panel hover:text-ink"
        >
          {section.label}
        </a>
      ))}
    </nav>
  );
}

export function SettingsSection({ children, id, kicker, title }: { children: ReactNode; id: string; kicker: string; title: string }) {
  return (
    <section id={`settings-${id}`} className="scroll-mt-32 rounded-sm border border-border bg-canvas/45">
      <div className="border-b border-border/70 bg-panel/80 px-4 py-3">
        <div className="text-xs font-semibold uppercase text-brand">{kicker}</div>
        <h3 className="mt-1 text-base font-bold text-ink">{title}</h3>
      </div>
      <div className="grid gap-4 p-4">{children}</div>
    </section>
  );
}

export function SettingsSaveBar({
  dirty,
  pending,
  valid,
  status,
  onReset,
  onSave,
}: {
  dirty: boolean;
  pending: boolean;
  valid: boolean;
  status?: ReactNode;
  onReset: () => void;
  onSave: () => void;
}) {
  return (
    <div className="sticky bottom-3 z-10 rounded-sm border border-border bg-panel/95 p-3 shadow-lg shadow-black/10 backdrop-blur">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div className="text-sm">
          <div className="font-semibold text-ink">{dirty ? "Unsaved settings changes" : "Settings are current"}</div>
          <div className="text-xs text-muted">{valid ? "General settings can be saved here. Account limits save in their own section." : "Fix validation before saving."}</div>
        </div>
        <div className="flex flex-wrap items-center gap-2">
          {status}
          {dirty ? (
            <button
              type="button"
              className="inline-flex items-center gap-2 rounded-sm border border-border bg-panel px-3 py-2 text-sm font-semibold text-muted"
              onClick={onReset}
            >
              <RotateCcw className="h-4 w-4" />
              Reset changes
            </button>
          ) : <StatusPill>Clean</StatusPill>}
          <button
            type="button"
            className="inline-flex items-center gap-2 rounded-sm border border-brand/40 bg-brand px-3 py-2 text-sm font-semibold text-white disabled:opacity-60 dark:text-slate-950"
            disabled={pending || !valid || !dirty}
            onClick={onSave}
          >
            {pending ? <RefreshCw className="h-4 w-4 animate-spin" /> : <Save className="h-4 w-4" />}
            Save settings
          </button>
        </div>
      </div>
    </div>
  );
}
