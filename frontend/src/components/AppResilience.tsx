import { Component, type ErrorInfo, type ReactNode } from "react";
import { RefreshCw, TriangleAlert } from "lucide-react";

type ErrorBoundaryProps = {
  children: ReactNode;
};

type ErrorBoundaryState = {
  error: Error | null;
};

function reloadPage() {
  window.location.reload();
}

export function RuntimeReloadPanel({
  details,
  title = "The dashboard needs a reload",
}: {
  details?: string;
  title?: string;
}) {
  return (
    <div className="grid min-h-screen place-items-center bg-canvas px-4 text-ink">
      <div className="w-full max-w-xl rounded-lg border border-border bg-panel p-6 shadow-lg">
        <div className="flex items-start gap-3">
          <TriangleAlert className="mt-1 h-5 w-5 shrink-0 text-accent" />
          <div className="min-w-0">
            <h1 className="text-xl font-bold tracking-normal">{title}</h1>
            <p className="mt-2 text-sm text-muted">
              {details || "The local server restarted or the loaded UI bundle is no longer current."}
            </p>
          </div>
        </div>
        <button
          type="button"
          onClick={reloadPage}
          className="mt-5 inline-flex items-center gap-2 rounded-md border border-border bg-brand px-3 py-2 text-sm font-semibold text-white dark:text-slate-950"
        >
          <RefreshCw className="h-4 w-4" />
          Reload
        </button>
      </div>
    </div>
  );
}

export class AppErrorBoundary extends Component<ErrorBoundaryProps, ErrorBoundaryState> {
  state: ErrorBoundaryState = { error: null };

  static getDerivedStateFromError(error: Error): ErrorBoundaryState {
    return { error };
  }

  componentDidCatch(error: Error, info: ErrorInfo) {
    console.error("dashboard_runtime_error", error, info.componentStack);
  }

  render() {
    if (this.state.error) {
      return (
        <RuntimeReloadPanel
          details={this.state.error.message || "The dashboard hit a runtime error after the page loaded."}
          title="The dashboard stopped rendering"
        />
      );
    }
    return this.props.children;
  }
}
