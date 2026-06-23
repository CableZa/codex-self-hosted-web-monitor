import { useEffect, useRef } from "react";
import { Info, X } from "lucide-react";
import { signalDescriptions, type SessionSignalThresholds } from "../lib/sessionSignalThresholds";

export function SignalInfoButton({
  open,
  title,
}: {
  open: () => void;
  title: string;
}) {
  return (
    <button
      type="button"
      className="inline-flex h-7 w-7 items-center justify-center rounded-md border border-border bg-panel text-muted hover:border-brand hover:text-brand"
      onClick={open}
      title={title}
    >
      <Info className="h-4 w-4" />
      <span className="sr-only">{title}</span>
    </button>
  );
}

export function SignalInfoDialog({ onClose, thresholds }: { onClose: () => void; thresholds?: SessionSignalThresholds }) {
  const dialogRef = useRef<HTMLDivElement>(null);
  const closeButtonRef = useRef<HTMLButtonElement>(null);

  useEffect(() => {
    const previousFocus = document.activeElement instanceof HTMLElement ? document.activeElement : null;
    const focusTimer = window.setTimeout(() => closeButtonRef.current?.focus(), 0);
    const handleKeyDown = (event: KeyboardEvent) => {
      if (event.key === "Escape") {
        onClose();
        return;
      }
      if (event.key !== "Tab" || !dialogRef.current) return;
      const focusable = Array.from(
        dialogRef.current.querySelectorAll<HTMLElement>(
          'a[href], button:not([disabled]), textarea:not([disabled]), input:not([disabled]), select:not([disabled]), [tabindex]:not([tabindex="-1"])',
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
      window.clearTimeout(focusTimer);
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
        aria-labelledby="session-signal-title"
        tabIndex={-1}
        onClick={(event) => event.stopPropagation()}
      >
        <div className="mb-4 flex items-start justify-between gap-3">
          <div>
            <h2 id="session-signal-title" className="text-lg font-bold text-ink">Session signal thresholds</h2>
            <p className="mt-1 text-sm text-muted">These are triage heuristics for spotting unusually heavy sessions, not billing rules or quality judgments.</p>
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
        <dl className="grid gap-3 text-sm">
          {Object.entries(signalDescriptions(thresholds)).map(([label, description]) => (
            <div key={label} className="rounded-md border border-border bg-canvas/60 p-3">
              <dt className="font-semibold capitalize text-ink">{label}</dt>
              <dd className="mt-1 text-muted">{description}</dd>
            </div>
          ))}
        </dl>
        <div className="mt-4 rounded-md border border-border bg-canvas/60 p-3 text-sm text-muted">
          Thresholds are configurable in Settings. The defaults stay conservative for normal Codex usage, while teams that routinely run million-token workflows can tune the signal sensitivity.
        </div>
      </div>
    </div>
  );
}
