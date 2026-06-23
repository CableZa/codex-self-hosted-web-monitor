import { describe, expect, it } from "vitest";
import type { AccountLimitStatus, AccountsReport } from "./apiTypes";
import {
  accountLimitExceeded,
  accountLimitUnderPressure,
  burnAdvisoriesForAccount,
  dismissSignal,
  focusedMonitorAccount,
  hiddenDismissedSignalCount,
  latestObservedAccount,
  monitorAccountOptions,
  shouldShowMonitorAccountSelector,
  signalSignature,
  statusForAccount,
  visibleDismissedSignals,
} from "./accountMonitoring";

function accountsReport(overrides: Partial<AccountsReport> = {}): AccountsReport {
  return {
    accounts: [
      {
        account: "work@example.com",
        source: "manual",
        first_seen: "2026-06-01T10:00:00+00:00",
        last_seen: "2026-06-03T10:00:00+00:00",
      },
      {
        account: "ops@example.com",
        source: "manual",
        first_seen: "2026-06-01T10:00:00+00:00",
        last_seen: "2026-06-02T10:00:00+00:00",
      },
    ],
    snapshots: [
      {
        observed_at: "2026-06-02T10:00:00+00:00",
        email: "ops@example.com",
        source: "manual",
      },
      {
        observed_at: "2026-06-03T10:00:00+00:00",
        email: "work@example.com",
        source: "manual",
      },
    ],
    ...overrides,
  };
}

function status(account: string, overrides: Partial<AccountLimitStatus> = {}): AccountLimitStatus {
  return {
    id: account === "work@example.com" ? 1 : 2,
    account,
    metric: "total_credits",
    cap_value: 500,
    current_value: 250,
    ratio: 0.5,
    remaining_value: 250,
    window_start: "2026-06-06",
    window_end: "2026-06-12",
    window_start_at: "2026-06-06T00:00:00+00:00",
    window_end_at: "2026-06-13T00:00:00+00:00",
    reset_at: "2026-06-13T00:00:00+00:00",
    reset_weekday: 4,
    reset_time: "00:00",
    timezone: "UTC",
    thresholds: [0.7, 0.85, 0.95, 1.0],
    crossed_thresholds: [],
    next_threshold: 0.7,
    exceeded: false,
    enabled: true,
    elapsed_days: 3,
    remaining_days: 5,
    safe_daily_spend: 50,
    spend_rate_vs_target: 1,
    projected_exhaustion_date: null,
    projected_exhaustion_label: "Not projected this window",
    burn_severity: "ok",
    burn_advisories: [],
    ...overrides,
  };
}

describe("account monitoring helpers", () => {
  it("uses the latest confirmed auth snapshot as the default monitor account", () => {
    expect(latestObservedAccount(accountsReport())).toBe("work@example.com");
    expect(focusedMonitorAccount(accountsReport(), [status("ops@example.com")], "")).toBe("work@example.com");
  });

  it("keeps a valid manual override and falls back when invalid", () => {
    const statuses = [status("work@example.com"), status("ops@example.com")];

    expect(focusedMonitorAccount(accountsReport(), statuses, "ops@example.com")).toBe("ops@example.com");
    expect(focusedMonitorAccount(accountsReport(), statuses, "missing@example.com")).toBe("work@example.com");
  });

  it("builds monitor options from the active account plus configured statuses", () => {
    expect(monitorAccountOptions(accountsReport(), [status("ops@example.com")])).toEqual([
      "work@example.com",
      "ops@example.com",
    ]);
  });

  it("filters orphaned status accounts out of the monitor options", () => {
    expect(
      monitorAccountOptions(accountsReport(), [status("ops@example.com"), status("orphan@example.com")]),
    ).toEqual(["work@example.com", "ops@example.com"]);
  });

  it("returns the matching status and burn advisories for the focused account", () => {
    const statuses = [
      status("work@example.com", {
        burn_advisories: [
          {
            id: "projected-exhaustion",
            severity: "warning",
            message: "At current pace you will run out by Thursday.",
            label: "Projected",
            value: "Thursday",
          },
        ],
      }),
    ];

    expect(statusForAccount(statuses, "work@example.com")?.account).toBe("work@example.com");
    expect(burnAdvisoriesForAccount(statuses[0]).map((item) => item.id)).toEqual(["projected-exhaustion"]);
  });

  it("evaluates limit pressure only from the focused status", () => {
    expect(accountLimitUnderPressure(status("work@example.com", { ratio: 0.81 }))).toBe(true);
    expect(accountLimitExceeded(status("work@example.com", { exceeded: true, ratio: 1.02 }))).toBe(true);
    expect(accountLimitUnderPressure(status("work@example.com", { ratio: 0.5 }))).toBe(false);
  });

  it("shows the monitor selector only when there is a real choice", () => {
    expect(shouldShowMonitorAccountSelector([])).toBe(false);
    expect(shouldShowMonitorAccountSelector(["work@example.com"])).toBe(false);
    expect(shouldShowMonitorAccountSelector(["work@example.com", "ops@example.com"])).toBe(true);
  });

  it("hides dismissed dashboard signals only while the same signal fingerprint still matches", () => {
    const rows = [
      { id: "attribution", signature: signalSignature("attribution", true, "Attribution looks current") },
      { id: "waste", signature: signalSignature("waste", true, "No obvious credit leaks") },
      { id: "limits", signature: signalSignature("limits", false, "Account limits need review") },
    ];
    const dismissed = dismissSignal({}, rows[0]);

    expect(visibleDismissedSignals(rows, dismissed).map((row) => row.id)).toEqual(["waste", "limits"]);
    expect(hiddenDismissedSignalCount(rows, dismissed)).toBe(1);
  });

  it("brings a dismissed signal back when its content changes", () => {
    const dismissed = {
      limits: signalSignature("limits", false, "Account limits need review", "warning"),
    };
    const rows = [
      { id: "limits", signature: signalSignature("limits", false, "Account limits need review", "critical") },
    ];

    expect(visibleDismissedSignals(rows, dismissed).map((row) => row.id)).toEqual(["limits"]);
    expect(hiddenDismissedSignalCount(rows, dismissed)).toBe(0);
  });
});
