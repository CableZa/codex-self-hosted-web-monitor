import { useEffect, useRef } from "react";
import { ScrollText, X } from "lucide-react";
import type { ChangelogReport } from "../lib/apiTypes";
import { LoaderBlock } from "./DashboardPrimitives";

export function ChangelogDialog({
  changelog,
  error,
  loading,
  onClose,
}: {
  changelog?: ChangelogReport;
  error?: Error | null;
  loading: boolean;
  onClose: () => void;
}) {
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

  const releases = changelog?.releases || [];

  return (
    <div className="fixed inset-0 z-40 flex items-center justify-center bg-black/60 p-4" role="presentation" onClick={onClose}>
      <div
        ref={dialogRef}
        className="max-h-[90vh] w-full max-w-3xl overflow-auto rounded-lg border border-border bg-panel p-5 shadow-xl"
        role="dialog"
        aria-modal="true"
        aria-labelledby="changelog-title"
        tabIndex={-1}
        onClick={(event) => event.stopPropagation()}
      >
        <div className="mb-4 flex items-start justify-between gap-3">
          <div>
            <div className="mb-1 inline-flex items-center gap-2 text-sm font-semibold text-brand">
              <ScrollText className="h-4 w-4" />
              Changelog
            </div>
            <h2 id="changelog-title" className="text-lg font-bold text-ink">What's new</h2>
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

        {loading ? <LoaderBlock label="Loading changelog" /> : null}
        {error ? (
          <div className="rounded-lg border border-danger/40 bg-danger/10 p-3 text-sm text-danger">
            {error.message}
          </div>
        ) : null}
        {!loading && !error && !releases.length ? (
          <div className="rounded-lg border border-border bg-canvas/60 p-4 text-sm text-muted">No changelog entries found.</div>
        ) : null}
        <div className="grid gap-4">
          {releases.map((release) => (
            <section key={`${release.version}-${release.date}`} className="rounded-lg border border-border bg-canvas/60 p-4">
              <div className="mb-3 flex flex-wrap items-baseline justify-between gap-2">
                <h3 className="text-base font-bold text-ink">{release.version ? `v${release.version}` : release.title}</h3>
                {release.date ? <span className="text-sm font-semibold text-muted">{release.date}</span> : null}
              </div>
              <div className="grid gap-3">
                {release.groups.map((group) => (
                  <div key={group.name}>
                    <div className="mb-1 text-sm font-semibold text-brand">{group.name}</div>
                    <ul className="grid gap-1 text-sm text-muted">
                      {group.items.map((item) => (
                        <li key={item} className="break-words">{item}</li>
                      ))}
                    </ul>
                  </div>
                ))}
              </div>
            </section>
          ))}
        </div>
      </div>
    </div>
  );
}
