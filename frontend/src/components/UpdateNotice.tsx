import { Clipboard, Server, X } from "lucide-react";
import { useMemo, useState } from "react";
import type { UpdateStatus } from "../lib/apiTypes";
import { formatDateTime } from "../lib/format";
import { shouldShowUpdateNotice, updateNoticeSignature } from "../lib/updateNotice";

type UpdateNoticeProps = {
  updateStatus?: UpdateStatus;
  dismissedSignature: string;
  onDismiss: (signature: string) => void;
};

export function UpdateNotice({ updateStatus, dismissedSignature, onDismiss }: UpdateNoticeProps) {
  const [copied, setCopied] = useState(false);
  const signature = updateNoticeSignature(updateStatus);
  const command = updateStatus?.manual_update_command || "python scripts/update-monitor.py apply";
  const title = updateStatus?.latest_version ? `Update v${updateStatus.latest_version} available` : "Update available";
  const checkedAt = updateStatus?.checked_at || updateStatus?.generated_at;
  const showNotice = shouldShowUpdateNotice(updateStatus, dismissedSignature);

  const versionDetail = useMemo(() => {
    const running = updateStatus?.running_version || updateStatus?.current_version;
    const latest = updateStatus?.latest_version;
    if (running && latest) return `Running v${running}. Latest is v${latest}.`;
    if (latest) return `Latest is v${latest}.`;
    return updateStatus?.message || "A newer release is ready.";
  }, [updateStatus?.current_version, updateStatus?.latest_version, updateStatus?.message, updateStatus?.running_version]);

  if (!showNotice || !updateStatus) return null;

  async function copyCommand() {
    try {
      await navigator.clipboard?.writeText(command);
      setCopied(true);
      window.setTimeout(() => setCopied(false), 1800);
    } catch {
      setCopied(false);
    }
  }

  return (
    <section className="overflow-hidden rounded-md border border-accent/40 bg-panel shadow-sm" aria-live="polite">
      <div className="h-1 bg-accent" />
      <div className="grid gap-3 p-3 sm:grid-cols-[auto_1fr_auto] sm:items-center sm:p-4">
        <div className="flex h-10 w-10 items-center justify-center rounded-md border border-accent/30 bg-accent/10 text-accent">
          <Server className="h-5 w-5" aria-hidden="true" />
        </div>
        <div className="min-w-0">
          <div className="flex flex-wrap items-center gap-x-3 gap-y-1">
            <h2 className="text-sm font-bold text-ink">{title}</h2>
            {updateStatus.latest_tag ? <span className="rounded-sm border border-border bg-canvas px-2 py-0.5 text-xs font-semibold text-muted">{updateStatus.latest_tag}</span> : null}
          </div>
          <p className="mt-1 text-sm text-muted">{versionDetail} Run the update manually from the repo root when ready.</p>
          <div className="mt-2 flex min-w-0 flex-wrap items-center gap-2">
            <code className="min-w-0 max-w-full overflow-x-auto rounded-sm border border-border bg-canvas px-2.5 py-1.5 text-xs font-semibold text-ink">{command}</code>
            {checkedAt ? <span className="text-xs font-semibold text-muted">Checked {formatDateTime(checkedAt)}</span> : null}
          </div>
        </div>
        <div className="flex items-center gap-2 sm:justify-end">
          <button
            type="button"
            className="inline-flex items-center gap-2 rounded-sm border border-accent/40 bg-accent/10 px-3 py-2 text-sm font-semibold text-accent"
            onClick={copyCommand}
          >
            <Clipboard className="h-4 w-4" aria-hidden="true" />
            {copied ? "Copied" : "Copy"}
          </button>
          <button
            type="button"
            className="inline-flex h-9 w-9 items-center justify-center rounded-sm border border-border bg-panel text-muted hover:border-accent hover:text-accent"
            onClick={() => onDismiss(signature)}
            aria-label="Hide this update"
          >
            <X className="h-4 w-4" aria-hidden="true" />
          </button>
        </div>
      </div>
    </section>
  );
}
