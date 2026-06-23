import { describe, expect, it } from "vitest";
import type { AccountLimitsReport, AccountsReport } from "./apiTypes";
import {
  attributionIssueCopy,
  confirmedAccounts,
  defaultBaselineAccount,
  defaultBaselineTimestampValue,
  prioritizedAttributionIssues,
  shouldAutoShowBaselineSnapshotForm,
  unconfirmedAccountLimits,
} from "./accountAttribution";

function accountsReport(overrides: Partial<AccountsReport> = {}): AccountsReport {
  return {
    accounts: [
      {
        account: "unknown",
        source: "usage",
      },
      {
        account: "work@example.com",
        source: "manual",
        first_seen: "2026-06-01T10:00:00+00:00",
        last_seen: "2026-06-03T10:00:00+00:00",
      },
      {
        account: "shadow@example.com",
        source: "usage",
      },
    ],
    snapshots: [
      {
        observed_at: "2026-06-03T10:00:00+00:00",
        email: "work@example.com",
        source: "manual",
      },
      {
        observed_at: "2026-06-01T10:00:00+00:00",
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
      issues: [
        {
          type: "late_first_snapshot",
          severity: "info",
          recommended_action: "add_manual_baseline_snapshot",
          earliest_usage_day: "2026-02-01",
          first_auth_snapshot_at: "2026-06-01T10:00:00+00:00",
        },
        {
          type: "unknown_usage_before_first_snapshot",
          severity: "warning",
          recommended_action: "add_manual_baseline_snapshot",
          earliest_usage_day: "2026-02-01",
          first_auth_snapshot_at: "2026-06-01T10:00:00+00:00",
        },
      ],
    },
    ...overrides,
  };
}

describe("account attribution helpers", () => {
  it("filters confirmed accounts from snapshot-backed options only", () => {
    expect(confirmedAccounts(accountsReport()).map((option) => option.account)).toEqual(["work@example.com"]);
  });

  it("chooses the earliest confirmed snapshot account and earliest unattributed day by default", () => {
    const report = accountsReport();

    expect(defaultBaselineAccount(report)).toBe("work@example.com");
    expect(defaultBaselineTimestampValue(report)).toBe("2026-02-01T00:00");
    expect(shouldAutoShowBaselineSnapshotForm(report)).toBe(true);
  });

  it("keeps the baseline timestamp blank when no baseline backfill issue exists", () => {
    const report = accountsReport({
      attribution: {
        history: {
          earliest_usage_day: "2026-02-01",
          latest_usage_day: "2026-06-03",
          first_auth_snapshot_at: "2026-06-01T10:00:00+00:00",
          visible_rollout_files: 48,
          sessions_root_files: 30,
          archived_sessions_root_files: 18,
        },
        issues: [],
      },
    });

    expect(defaultBaselineTimestampValue(report)).toBe("");
    expect(shouldAutoShowBaselineSnapshotForm(report)).toBe(false);
  });

  it("keeps the baseline form collapsed for non-baseline attribution issues", () => {
    const report = accountsReport({
      attribution: {
        history: {
          earliest_usage_day: "2026-02-01",
          latest_usage_day: "2026-06-03",
          first_auth_snapshot_at: "2026-06-01T10:00:00+00:00",
          visible_rollout_files: 8,
          sessions_root_files: 30,
          archived_sessions_root_files: 18,
        },
        issues: [
          {
            type: "sparse_visible_history",
            severity: "warning",
            recommended_action: "check_codex_host_home_mount",
          },
        ],
      },
    });

    expect(defaultBaselineTimestampValue(report)).toBe("");
    expect(shouldAutoShowBaselineSnapshotForm(report)).toBe(false);
  });

  it("sorts higher-priority attribution issues first", () => {
    expect(prioritizedAttributionIssues(accountsReport().attribution).map((issue) => issue.type)).toEqual([
      "unknown_usage_before_first_snapshot",
      "late_first_snapshot",
    ]);
  });

  it("summarizes sparse mount issues with practical copy", () => {
    expect(
      attributionIssueCopy({
        type: "sparse_visible_history",
        severity: "warning",
        recommended_action: "check_codex_host_home_mount",
      }).title,
    ).toBe("Visible history looks incomplete");
  });

  it("keeps unconfirmed stored limits visible but separate from editable confirmed accounts", () => {
    const report: AccountLimitsReport = {
      limits: [
        {
          account: "legacy@example.com",
          metric: "total_credits",
          cap_value: 200,
          reset_weekday: 4,
          reset_time: "00:00",
          timezone: "UTC",
          thresholds: [0.7, 0.85, 0.95, 1.0],
          enabled: false,
        },
      ],
      statuses: [],
    };

    expect(unconfirmedAccountLimits(report, accountsReport()).map((limit) => limit.account)).toEqual(["legacy@example.com"]);
  });
});
