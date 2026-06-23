import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it } from "vitest";
import type { AccountLimitsReport, AccountsReport } from "../lib/apiTypes";
import { AccountLimitSettings } from "./AccountLimits";

const accounts: AccountsReport = {
  accounts: [
    {
      account: "work@example.com",
      email: "work@example.com",
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
};

const report: AccountLimitsReport = {
  status_state: "refreshing",
  limits: [
    {
      id: 1,
      account: "work@example.com",
      metric: "total_credits",
      cap_value: 5000,
      reset_weekday: 4,
      reset_time: "00:00",
      timezone: "UTC",
      thresholds: [0.7, 0.85],
      enabled: true,
    },
  ],
  statuses: [],
};

function renderSettings(nextAccounts: AccountsReport = accounts, nextReport: AccountLimitsReport = report) {
  const client = new QueryClient();
  return renderToStaticMarkup(
    <QueryClientProvider client={client}>
      <AccountLimitSettings accounts={nextAccounts} report={nextReport} />
    </QueryClientProvider>,
  );
}

describe("AccountLimitSettings", () => {
  it("shows a refreshing notice when status is not ready", () => {
    expect(renderSettings()).toContain("Usage status is refreshing");
  });

  it("uses API-provided auto limit defaults for matching accounts", () => {
    const autoAccounts: AccountsReport = {
      ...accounts,
      accounts: [{ ...accounts.accounts[0], account: "work@auto-limit.example", email: "work@auto-limit.example" }],
      auto_account_limit_defaults: {
        email_suffixes: ["@auto-limit.example"],
        cap_credits: 400,
        reset_weekday: 4,
        reset_time: "00:00",
        timezone: "UTC",
        thresholds: [0.7, 0.85, 0.95, 1.0],
      },
    };
    const emptyReport: AccountLimitsReport = { status_state: "ready", limits: [], statuses: [] };

    const html = renderSettings(autoAccounts, emptyReport);

    expect(html).toContain('value="400"');
    expect(html).toContain("Every Friday at 00:00 UTC");
  });
});
