import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it } from "vitest";
import { SessionAnalyticsControls } from "./SessionFilters";

describe("SessionAnalyticsControls", () => {
  it("renders active filter chips and clear action", () => {
    const html = renderToStaticMarkup(
      <SessionAnalyticsControls
        accountFilter="work@example.com"
        accounts={["work@example.com"]}
        longContextOnly
        modelFilter="gpt-5.5"
        models={["gpt-5.5"]}
        projectFilter="codex-self-hosted-web-monitor"
        projects={["codex-self-hosted-web-monitor"]}
        search="token spike"
        setAccountFilter={() => undefined}
        setLongContextOnly={() => undefined}
        setModelFilter={() => undefined}
        setProjectFilter={() => undefined}
        setSearch={() => undefined}
        setSortMode={() => undefined}
        setUncachedHeavyOnly={() => undefined}
        setWasteReasonFilter={() => undefined}
        showAccountFilter
        signalThresholds={{
          highInputTokens: 1000000,
          highUncachedInputTokens: 500000,
          lowCacheMinUncachedTokens: 100000,
          lowCacheMaxReuseRatio: 0.5,
          largeTotalTokens: 1000000,
          highOutputTokens: 50000,
          longContextPricingSignalEnabled: true,
        }}
        sortMode="credits"
        uncachedHeavyOnly
        wasteReasonFilter=""
      />,
    );

    expect(html).toContain("Clear filters");
    expect(html).toContain("Search: token spike");
    expect(html).toContain("Rank: credits");
    expect(html).toContain("Model: gpt-5.5");
    expect(html).toContain("Long context");
    expect(html).toContain("Low cache reuse");
  });
});
