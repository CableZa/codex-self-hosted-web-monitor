import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it } from "vitest";
import type { AccountsReport, AttributionIssue } from "../lib/apiTypes";
import { AccountAttributionPanel } from "./AccountAttributionPanel";

function accountsReport(issues: AttributionIssue[]): AccountsReport {
  return {
    accounts: [
      {
        account: "work@example.com",
        source: "manual",
        first_seen: "2026-06-01T10:00:00+00:00",
        last_seen: "2026-06-03T10:00:00+00:00",
      },
    ],
    snapshots: [
      {
        observed_at: "2026-06-03T10:00:00+00:00",
        email: "work@example.com",
        source: "manual",
      },
    ],
    attribution: {
      history: {
        earliest_usage_day: "2026-02-01",
        latest_usage_day: "2026-06-03",
        first_auth_snapshot_at: "2026-06-01T10:00:00+00:00",
        visible_rollout_files: 48,
        sessions_root_files: 30,
        archived_sessions_root_files: 18,
      },
      issues,
    },
  };
}

function renderPanel(accounts: AccountsReport) {
  const client = new QueryClient();

  return renderToStaticMarkup(
    <QueryClientProvider client={client}>
      <AccountAttributionPanel accounts={accounts} />
    </QueryClientProvider>,
  );
}

describe("AccountAttributionPanel", () => {
  it("keeps the baseline form collapsed for non-baseline issues initially", () => {
    const html = renderPanel(accountsReport([
      {
        type: "sparse_visible_history",
        severity: "warning",
        recommended_action: "check_codex_host_home_mount",
      },
    ]));

    expect(html).toContain("Open form");
    expect(html).toContain("Only use this when you want to deliberately backfill older usage.");
    expect(html).toContain("Advanced");
    expect(html).not.toContain("Effective date and time (UTC)");
  });

  it("shows the baseline form immediately when attribution recommends a backfill", () => {
    const html = renderPanel(accountsReport([
      {
        type: "unknown_usage_before_first_snapshot",
        severity: "warning",
        recommended_action: "add_manual_baseline_snapshot",
        earliest_usage_day: "2026-02-01",
        first_auth_snapshot_at: "2026-06-01T10:00:00+00:00",
      },
    ]));

    expect(html).toContain("Effective date and time (UTC)");
    expect(html).toContain("Add baseline");
    expect(html).not.toContain("Keep this hidden unless you need a deliberate backfill for older usage.");
  });
});
