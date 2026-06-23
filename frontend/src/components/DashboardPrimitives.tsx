import { useEffect, useRef, type ReactNode } from "react";
import { StatusPill } from "./StatusPill";
import { Spinner } from "./Spinner";

export function QueryStateBar({ loading, fetching, error }: { loading: boolean; fetching: boolean; error?: Error | null }) {
  if (loading) return <StatusPill tone="loading">Loading data</StatusPill>;
  if (error) return <StatusPill tone="warn">Request failed</StatusPill>;
  if (fetching) return <StatusPill tone="loading">Refreshing data</StatusPill>;
  return <StatusPill>Live</StatusPill>;
}

export function MetricCard({ label, value, icon }: { label: string; value: string; icon: ReactNode }) {
  return (
    <div className="rounded-md border border-border bg-panel/95 p-3 shadow-sm">
      <div className="flex items-center gap-2 text-xs font-semibold uppercase tracking-normal text-muted">
        {icon}
        <span>{label}</span>
      </div>
      <div className="mt-1 break-words text-2xl font-bold tracking-normal text-brand">{value}</div>
    </div>
  );
}

export function LoaderBlock({ label }: { label: string }) {
  return (
    <div className="flex min-h-40 items-center justify-center rounded-lg border border-dashed border-border bg-canvas/50">
      <Spinner label={label} />
    </div>
  );
}

export function DataLoadingOverlay({ label }: { label: string }) {
  const dialogRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    const previousFocus = document.activeElement instanceof HTMLElement ? document.activeElement : null;
    const timer = window.setTimeout(() => dialogRef.current?.focus(), 0);
    const handleKeyDown = (event: KeyboardEvent) => {
      if (event.key !== "Tab") return;
      event.preventDefault();
      dialogRef.current?.focus();
    };
    window.addEventListener("keydown", handleKeyDown);
    return () => {
      window.clearTimeout(timer);
      window.removeEventListener("keydown", handleKeyDown);
      previousFocus?.focus();
    };
  }, []);

  return (
    <div
      ref={dialogRef}
      className="fixed inset-0 z-30 flex items-center justify-center bg-canvas/45 px-4 backdrop-blur-sm"
      role="dialog"
      aria-modal="true"
      aria-label={label}
      tabIndex={-1}
    >
      <div className="w-full max-w-xs rounded-lg border border-border bg-panel p-4 shadow-xl" role="status" aria-live="polite">
        <Spinner label={label} />
        <div className="mt-3 h-1.5 overflow-hidden rounded-full bg-border/70">
          <div className="h-full w-full animate-pulse rounded-full bg-brand" />
        </div>
      </div>
    </div>
  );
}

export function ErrorBlock({ message }: { message: string }) {
  return <div className="rounded-lg border border-danger/40 bg-danger/10 p-4 text-sm text-danger">{message}</div>;
}
