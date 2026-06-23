import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it } from "vitest";
import type { SessionHistoryReport } from "../lib/apiTypes";
import { SessionSummaryStrip } from "./SessionSummaryStrip";

const totals = {
  input_tokens: 1000,
  cached_input_tokens: 600,
  uncached_input_tokens: 400,
  output_tokens: 200,
  total_tokens: 1200,
  total_usd: 0,
  total_zar: 0,
  input_credits: 1,
  cached_input_credits: 1,
  output_credits: 1,
  total_credits: 12,
};

const sessions: SessionHistoryReport = {
  period: { from: "2026-06-01T00:00:00+00:00", to: "2026-06-02T00:00:00+00:00" },
  totals,
  sessions: [],
};

describe("SessionSummaryStrip", () => {
  it("renders scope and visible session counts", () => {
    const html = renderToStaticMarkup(
      <SessionSummaryStrip
        scopeLabel="All accounts"
        sessionRowsCount={12}
        sessions={sessions}
        sessionsFetching={false}
        visibleCount={5}
      />,
    );

    expect(html).toContain("Session Scope");
    expect(html).toContain("All accounts");
    expect(html).toContain("5 visible");
    expect(html).toContain("Filtered result");
  });
});
