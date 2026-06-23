import { describe, expect, it } from "vitest";
import { cacheBackendLabel, cacheBackendName, groupedUsageRowsForReport, rangeTotals, usesMemoryCache } from "./usage";

describe("cache backend helpers", () => {
  it("reads a direct backend name", () => {
    const cache = { backend: "memory", ok: true };

    expect(cacheBackendName(cache)).toBe("memory");
    expect(cacheBackendLabel(cache)).toBe("memory");
    expect(usesMemoryCache(cache)).toBe(true);
  });

  it("reads a nested backend name from cached snapshot payloads", () => {
    const cache = { backend: { backend: "memory", ok: true }, response: { hit: true, ttl_seconds: 90, served_at: "2026-06-08T10:00:00Z" } };

    expect(cacheBackendName(cache)).toBe("memory");
    expect(cacheBackendLabel(cache)).toBe("memory");
    expect(usesMemoryCache(cache)).toBe(true);
  });

  it("does not treat non-memory backends as degraded", () => {
    const cache = { backend: "valkey", ok: true };

    expect(cacheBackendName(cache)).toBe("valkey");
    expect(usesMemoryCache(cache)).toBe(false);
  });
});

describe("grouped usage rows", () => {
  it("prefers backend week and month rollups when present", () => {
    const report = {
      period: { from: "2026-06-01", to: "2026-06-02" },
      days: [
        { day: "2026-06-01", input_tokens: 1, output_tokens: 0, total_tokens: 1, total_usd: 0, total_zar: 0, input_credits: 0, output_credits: 0, total_credits: 1 },
        { day: "2026-06-02", input_tokens: 2, output_tokens: 0, total_tokens: 2, total_usd: 0, total_zar: 0, input_credits: 0, output_credits: 0, total_credits: 2 },
      ],
      weeks: [{ day: "2026-06-01", label: "server week", input_tokens: 3, output_tokens: 0, total_tokens: 3, total_usd: 0, total_zar: 0, input_credits: 0, output_credits: 0, total_credits: 3 }],
      months: [{ day: "2026-06", label: "server month", input_tokens: 3, output_tokens: 0, total_tokens: 3, total_usd: 0, total_zar: 0, input_credits: 0, output_credits: 0, total_credits: 3 }],
      exchange_rate: { rate: 18.5, source: "test", day: "2026-06-02" },
    };

    expect(groupedUsageRowsForReport(report, "week")[0].label).toBe("server week");
    expect(groupedUsageRowsForReport(report, "month")[0].label).toBe("server month");
    expect(groupedUsageRowsForReport(report, "day")).toHaveLength(2);
  });

  it("falls back to client grouping when backend rollups are missing", () => {
    const report = {
      period: { from: "2026-06-01", to: "2026-06-02" },
      days: [
        { day: "2026-06-01", input_tokens: 1, output_tokens: 0, total_tokens: 1, total_usd: 0, total_zar: 0, input_credits: 0, output_credits: 0, total_credits: 1 },
        { day: "2026-06-02", input_tokens: 2, output_tokens: 0, total_tokens: 2, total_usd: 0, total_zar: 0, input_credits: 0, output_credits: 0, total_credits: 2 },
      ],
      exchange_rate: { rate: 18.5, source: "test", day: "2026-06-02" },
    };

    const grouped = groupedUsageRowsForReport(report, "week");

    expect(grouped).toHaveLength(1);
    expect(grouped[0].total_tokens).toBe(3);
  });
});

describe("range totals", () => {
  it("preserves cache and credit fields for selected range overview stats", () => {
    const totals = rangeTotals([
      {
        day: "2026-06-01",
        input_tokens: 100,
        cached_input_tokens: 70,
        uncached_input_tokens: 30,
        output_tokens: 20,
        total_tokens: 120,
        total_usd: 1,
        total_zar: 18,
        input_credits: 10,
        cached_input_credits: 2,
        output_credits: 5,
        total_credits: 17,
      },
      {
        day: "2026-06-02",
        input_tokens: 50,
        cached_input_tokens: 10,
        uncached_input_tokens: 40,
        output_tokens: 15,
        total_tokens: 65,
        total_usd: 2,
        total_zar: 36,
        input_credits: 8,
        cached_input_credits: 1,
        output_credits: 4,
        total_credits: 13,
      },
    ]);

    expect(totals.cached_input_tokens).toBe(80);
    expect(totals.uncached_input_tokens).toBe(70);
    expect(totals.cached_input_credits).toBe(3);
    expect(totals.total_tokens).toBe(185);
    expect(totals.total_credits).toBe(30);
  });
});
