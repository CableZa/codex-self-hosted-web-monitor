import { describe, expect, it } from "vitest";
import type { Snapshot, UsageReport } from "./apiTypes";
import { snapshotBootstrapPending, snapshotDataPending, snapshotReport, snapshotReportsReady, snapshotRuntimeError } from "./snapshotState";

function usageReport(): UsageReport {
  return {
    totals: {
      input_tokens: 0,
      output_tokens: 0,
      total_tokens: 0,
      total_usd: 0,
      total_zar: 0,
      input_credits: 0,
      output_credits: 0,
      total_credits: 0,
    },
    by_model: [],
    by_effort: [],
    by_account: [],
    currency: { code: "ZAR", usd_zar: 18.5 },
    period: { from: "2026-06-01", to: "2026-06-01" },
    exchange_rate: { rate: 18.5, source: "disabled", day: "2026-06-01" },
    by_day: [],
    by_day_model: [],
    by_day_account: [],
    by_model_effort: [],
    warnings: [],
  };
}

function snapshot(overrides: Partial<Snapshot> = {}): Snapshot {
  return {
    generated_at: "2026-06-09T10:00:00+00:00",
    timezone: "UTC",
    reports: {
      today: usageReport(),
      week: usageReport(),
      month: usageReport(),
    },
    ...overrides,
  };
}

describe("snapshot state helpers", () => {
  it("treats warming snapshots without reports as not ready", () => {
    expect(snapshotReportsReady(snapshot({ status: "warming", reports: undefined }))).toBe(false);
    expect(snapshotReport(snapshot({ status: "warming", reports: undefined }), "today")).toBeUndefined();
  });

  it("treats full snapshots as ready", () => {
    expect(snapshotReportsReady(snapshot())).toBe(true);
    expect(snapshotReport(snapshot(), "today")?.totals.total_credits).toBe(0);
  });

  it("surfaces a scanner error message as a runtime error", () => {
    const error = snapshotRuntimeError(snapshot({ error: "scanner loop failed", reports: undefined }));

    expect(error?.message).toBe("scanner loop failed");
  });

  it("stops snapshot bootstrapping when a logical snapshot error exists", () => {
    const error = snapshotRuntimeError(snapshot({ error: "scanner loop failed", reports: undefined }));

    expect(snapshotBootstrapPending({ rangeTimezoneReady: false, runtimeError: error })).toBe(false);
  });

  it("stops snapshot pending state when the query itself fails", () => {
    expect(snapshotDataPending({
      reportsReady: false,
      queryError: new Error("request failed"),
    })).toBe(false);
  });

  it("keeps snapshot pending only while reports are still missing and no error exists", () => {
    expect(snapshotDataPending({ reportsReady: false })).toBe(true);
    expect(snapshotDataPending({ reportsReady: true })).toBe(false);
  });
});
