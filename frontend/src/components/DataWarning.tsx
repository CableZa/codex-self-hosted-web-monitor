import { AlertTriangle, X } from "lucide-react";
import { useLocalPreference } from "../lib/localPreference";

type DataWarningProps = {
  warnings: string[];
};

export function DataWarning({ warnings }: DataWarningProps) {
  const [dismissedWarnings, setDismissedWarnings] = useLocalPreference<Record<string, string>>("codex-monitor-dismissed-data-warnings", {});
  const visibleWarnings = warnings.filter((warning) => !dismissedWarnings[warning]);

  if (!visibleWarnings.length) return null;

  function dismissVisibleWarnings() {
    setDismissedWarnings((current) => {
      const next = { ...current };
      const dismissedAt = new Date().toISOString();
      visibleWarnings.forEach((warning) => {
        next[warning] = dismissedAt;
      });
      return next;
    });
  }

  return (
    <div className="rounded-sm border border-amber-500/50 bg-amber-500/10 p-4 text-sm text-amber-100">
      <div className="flex items-start justify-between gap-4">
        <div className="min-w-0">
          <div className="mb-2 inline-flex items-center gap-2 font-semibold text-amber-200">
            <AlertTriangle className="h-4 w-4 shrink-0" />
            Data warning
          </div>
          <ul className="grid gap-1">
            {visibleWarnings.map((warning) => (
              <li key={warning} className="break-words">{warning}</li>
            ))}
          </ul>
        </div>
        <button
          type="button"
          onClick={dismissVisibleWarnings}
          className="inline-flex h-8 w-8 shrink-0 items-center justify-center rounded-sm border border-amber-500/35 bg-panel/70 text-amber-200 hover:bg-amber-500/10"
          aria-label="Dismiss data warning"
        >
          <X className="h-4 w-4" />
        </button>
      </div>
    </div>
  );
}
