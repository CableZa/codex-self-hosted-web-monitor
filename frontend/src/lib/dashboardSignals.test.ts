import { describe, expect, it } from "vitest";
import type { SessionHistoryReport, SessionSummary, Snapshot } from "./apiTypes";
import {
  burnAdvisories,
  projectWasteRollups,
  sessionMatchesWasteReason,
  sessionWasteFindings,
  weeklyBudgetWindow,
  weeklyCreditRunway,
} from "./dashboardSignals";
import { visibleContextReasons } from "./sessionSignalThresholds";

function totals(overrides = {}) {
  return {
    input_tokens: 0,
    cached_input_tokens: 0,
    uncached_input_tokens: 0,
    output_tokens: 0,
    total_tokens: 0,
    total_usd: 0,
    total_zar: 0,
    input_credits: 0,
    cached_input_credits: 0,
    output_credits: 0,
    total_credits: 0,
    ...overrides,
  };
}

function snapshot(overrides: Partial<Snapshot> = {}): Snapshot {
  return {
    generated_at: "2026-06-03T10:00:00Z",
    timezone: "UTC",
    reports: {
      today: {
        period: { from: "2026-06-03T00:00:00Z", to: "2026-06-03T23:59:59Z" },
        totals: totals({ total_credits: 80 }),
        by_day: [],
        by_model: [],
        by_effort: [],
        by_account: [],
        by_day_model: [],
        by_day_account: [],
        by_model_effort: [],
        exchange_rate: { rate: 18, source: "disabled", day: "2026-06-03" },
      },
      week: {
        period: { from: "2026-06-01T00:00:00Z", to: "2026-06-07T23:59:59Z" },
        totals: totals({ total_credits: 240 }),
        by_day: [],
        by_model: [],
        by_effort: [],
        by_account: [],
        by_day_model: [],
        by_day_account: [],
        by_model_effort: [],
        exchange_rate: { rate: 18, source: "disabled", day: "2026-06-03" },
      },
      month: {
        period: { from: "2026-06-01T00:00:00Z", to: "2026-06-30T23:59:59Z" },
        totals: totals(),
        by_day: [],
        by_model: [],
        by_effort: [],
        by_account: [],
        by_day_model: [],
        by_day_account: [],
        by_model_effort: [],
        exchange_rate: { rate: 18, source: "disabled", day: "2026-06-03" },
      },
    },
    budgets: [
      {
        period: "week",
        start: "2026-06-01",
        end: "2026-06-07",
        budget_zar: 0,
        current_zar: 0,
        budget_credits: 700,
        current_credits: 240,
        unit: "credits",
        ratio: 0.34,
        exceeded: false,
      },
      {
        period: "today",
        start: "2026-06-03",
        end: "2026-06-03",
        budget_zar: 0,
        current_zar: 0,
        budget_credits: 100,
        current_credits: 80,
        unit: "credits",
        ratio: 0.8,
        exceeded: false,
      },
    ],
    ...overrides,
  };
}

function session(id: string, overrides: Partial<SessionSummary> = {}): SessionSummary {
  return {
    ...totals(),
    session_id: id,
    first_seen: "2026-06-03T09:00:00Z",
    last_seen: "2026-06-03T10:00:00Z",
    duration_seconds: 3600,
    accounts: ["work@example.com"],
    by_model: [],
    ...overrides,
  };
}

function history(sessions: SessionSummary[]): SessionHistoryReport {
  return {
    period: { from: "2026-06-01T00:00:00Z", to: "2026-06-07T23:59:59Z" },
    totals: totals({ total_credits: sessions.reduce((sum, row) => sum + Number(row.total_credits || 0), 0) }),
    sessions,
    by_project: [
      { ...totals({ total_credits: 420 }), project: "monitor", project_path: "/repo/monitor", sessions: 3 },
      { ...totals({ total_credits: 260 }), project: "monitor", project_path: "/repo/other", sessions: 3 },
    ],
  };
}

describe("weeklyCreditRunway", () => {
  it("returns null when the weekly budget is missing or unusable", () => {
    expect(weeklyCreditRunway(snapshot({ budgets: null }))).toBeNull();
    expect(weeklyCreditRunway(snapshot({ budgets: [] }))).toBeNull();
  });

  it("projects exhaustion inside the current week", () => {
    const runway = weeklyCreditRunway(snapshot({
      budgets: [
        {
          period: "week",
          start: "2026-06-01",
          end: "2026-06-07",
          budget_zar: 0,
          current_zar: 0,
          budget_credits: 300,
          current_credits: 240,
          unit: "credits",
          ratio: 0.8,
          exceeded: false,
        },
      ],
    }));

    expect(runway?.projectedExhaustionDate).toBe("2026-06-04");
    expect(runway?.severity).toBe("warning");
  });

  it("exposes the weekly budget window for chart gating", () => {
    expect(weeklyBudgetWindow(snapshot())).toEqual({ start: "2026-06-01", end: "2026-06-07" });
    expect(weeklyBudgetWindow(snapshot({ budgets: null }))).toBeNull();
  });
});

describe("burnAdvisories", () => {
  it("emits a today-over-target advisory", () => {
    const advisories = burnAdvisories(snapshot({
      budgets: [
        {
          period: "week",
          start: "2026-06-01",
          end: "2026-06-07",
          budget_zar: 0,
          current_zar: 0,
          budget_credits: 700,
          current_credits: 120,
          unit: "credits",
          ratio: 0.17,
          exceeded: false,
        },
        {
          period: "today",
          start: "2026-06-03",
          end: "2026-06-03",
          budget_zar: 0,
          current_zar: 0,
          budget_credits: 100,
          current_credits: 180,
          unit: "credits",
          ratio: 1.8,
          exceeded: true,
        },
      ],
    }));

    expect(advisories.some((advisory) => advisory.id === "today-over-target")).toBe(true);
  });
});

describe("session waste signals", () => {
  it("detects low-cache sessions and filters by waste reason", () => {
    const sessions = history([
      session("low", {
        uncached_input_tokens: 140_000,
        cache_efficiency: 0.2,
        total_credits: 60,
      }),
      session("quiet", { uncached_input_tokens: 10_000, cache_efficiency: 0.9, total_credits: 30 }),
    ]);

    expect(sessionMatchesWasteReason(sessions.sessions[0], sessions, "low-cache")).toBe(true);
    expect(sessionMatchesWasteReason(sessions.sessions[1], sessions, "low-cache")).toBe(false);
    expect(sessionWasteFindings(sessions, sessions.sessions, { reasonId: "low-cache" })).toHaveLength(1);
  });

  it("orders likely waste by derived score", () => {
    const sessions = history([
      session("small", { total_credits: 20, uncached_input_tokens: 120_000, cache_efficiency: 0.1 }),
      session("large", { total_credits: 180, uncached_input_tokens: 220_000, cache_efficiency: 0.1 }),
    ]);

    expect(sessionWasteFindings(sessions, sessions.sessions)[0].session.session_id).toBe("large");
  });

  it("uses backend waste findings when present", () => {
    const sessions = history([
      session("backend", {
        total_credits: 80,
        waste_findings: [
          {
            id: "retry-churn",
            severity: "warning",
            label: "Repeated tool retries",
            recommendation: "inspect the first failure",
            confidence: "medium",
            evidence: "3 repeated tool calls",
            estimated_waste_credits: 12,
            estimated_waste_usd: 0.5,
          },
        ],
      }),
    ]);

    expect(sessionMatchesWasteReason(sessions.sessions[0], sessions, "retry-churn")).toBe(true);
    expect(sessionWasteFindings(sessions, sessions.sessions)[0].reasons[0]).toMatchObject({
      id: "retry-churn",
      label: "Repeated tool retries",
    });
  });

  it("matches repeated projects by name and path", () => {
    const sessions = history([
      session("same-name-a", { project_name: "monitor", project_path: "/repo/monitor", total_credits: 120 }),
      session("same-name-b", { project_name: "monitor", project_path: "/repo/other", total_credits: 90 }),
    ]);

    const findings = sessionWasteFindings(sessions, sessions.sessions);
    expect(findings.find((finding) => finding.session.session_id === "same-name-a")?.reasons.map((reason) => reason.id)).toContain("repeated-project");
    expect(findings.find((finding) => finding.session.session_id === "same-name-b")?.reasons.map((reason) => reason.id)).toContain("repeated-project");
  });

  it("builds project-level waste rollups", () => {
    const sessions = history([
      session("one", { project_name: "monitor", project_path: "/repo/monitor", total_credits: 120, uncached_input_tokens: 220_000, cache_efficiency: 0.1 }),
      session("two", { project_name: "monitor", project_path: "/repo/monitor", total_credits: 80, output_tokens: 90_000 }),
    ]);

    const rollups = projectWasteRollups(sessions, sessions.sessions);
    expect(rollups[0]).toMatchObject({ project: "monitor", projectPath: "/repo/monitor", sessions: 2, wasteCredits: 200 });
  });

  it("uses supplied session signal thresholds", () => {
    const sessions = history([
      session("custom", { uncached_input_tokens: 210_000, cache_efficiency: 0.7, output_tokens: 80_000, total_credits: 40 }),
    ]);

    const findings = sessionWasteFindings(sessions, sessions.sessions, {
      thresholds: {
        highInputTokens: 1_000_000,
        highUncachedInputTokens: 200_000,
        lowCacheMinUncachedTokens: 100_000,
        lowCacheMaxReuseRatio: 0.5,
        largeTotalTokens: 1_500_000,
        highOutputTokens: 75_000,
        longContextPricingSignalEnabled: true,
      },
    });

    expect(findings[0].reasons.map((reason) => reason.id)).toEqual(["huge-uncached", "high-output"]);
  });

  it("hides long-context pricing signals when disabled", () => {
    const sessions = history([
      session("pricing", { long_context_applied: true, long_context_events: 1, total_credits: 40 }),
    ]);

    const findings = sessionWasteFindings(sessions, sessions.sessions, {
      thresholds: {
        highInputTokens: 1_000_000,
        highUncachedInputTokens: 250_000,
        lowCacheMinUncachedTokens: 100_000,
        lowCacheMaxReuseRatio: 0.5,
        largeTotalTokens: 1_500_000,
        highOutputTokens: 100_000,
        longContextPricingSignalEnabled: false,
      },
    });

    expect(findings).toHaveLength(0);
    expect(sessionMatchesWasteReason(sessions.sessions[0], sessions, "long-context", {
      highInputTokens: 1_000_000,
      highUncachedInputTokens: 250_000,
      lowCacheMinUncachedTokens: 100_000,
      lowCacheMaxReuseRatio: 0.5,
      largeTotalTokens: 1_500_000,
      highOutputTokens: 100_000,
      longContextPricingSignalEnabled: false,
    })).toBe(false);
    expect(visibleContextReasons(session("reason", { long_context_reasons: ["long-context pricing"] }), {
      highInputTokens: 1_000_000,
      highUncachedInputTokens: 250_000,
      lowCacheMinUncachedTokens: 100_000,
      lowCacheMaxReuseRatio: 0.5,
      largeTotalTokens: 1_500_000,
      highOutputTokens: 100_000,
      longContextPricingSignalEnabled: false,
    })).toEqual([]);
  });
});
