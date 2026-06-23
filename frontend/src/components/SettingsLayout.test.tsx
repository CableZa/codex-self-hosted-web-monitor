import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it } from "vitest";
import { SettingsSaveBar, SettingsSectionNav } from "./SettingsLayout";

describe("Settings layout", () => {
  it("renders section navigation anchors", () => {
    const html = renderToStaticMarkup(<SettingsSectionNav />);

    expect(html).toContain("#settings-usage");
    expect(html).toContain("#settings-appearance");
    expect(html).toContain("#settings-accounts");
    expect(html).toContain("#settings-limits");
    expect(html).toContain("#settings-sessions");
    expect(html).toContain("#settings-integrations");
  });

  it("renders dirty save state", () => {
    const html = renderToStaticMarkup(
      <SettingsSaveBar
        dirty
        pending={false}
        valid
        onReset={() => undefined}
        onSave={() => undefined}
      />,
    );

    expect(html).toContain("Unsaved settings changes");
    expect(html).toContain("Reset changes");
    expect(html).toContain("Save settings");
  });
});
