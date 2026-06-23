import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it, vi } from "vitest";
import type { UpdateStatus } from "../lib/apiTypes";
import { shouldShowUpdateNotice, updateNoticeSignature } from "../lib/updateNotice";
import { UpdateNotice } from "./UpdateNotice";

const updateStatus: UpdateStatus = {
  state: "update_available",
  generated_at: "2026-06-23T10:00:00+00:00",
  checked_at: "2026-06-23T10:00:00+00:00",
  current_version: "0.16.0",
  running_version: "0.16.0",
  latest_version: "0.17.0",
  latest_tag: "v0.17.0",
  install_mode: "docker",
  check_mode: "builtin_http",
  source_url: "https://example.test/tags",
  manual_update_command: "./scripts/update-and-redeploy",
  message: "Version 0.17.0 is available.",
};

describe("UpdateNotice", () => {
  it("renders the available update and manual command", () => {
    const html = renderToStaticMarkup(
      <UpdateNotice
        updateStatus={updateStatus}
        dismissedSignature=""
        onDismiss={vi.fn()}
      />,
    );

    expect(html).toContain("Update v0.17.0 available");
    expect(html).toContain("Running v0.16.0. Latest is v0.17.0.");
    expect(html).toContain("./scripts/update-and-redeploy");
    expect(html).toContain("Hide this update");
  });

  it("hides only the dismissed version signature", () => {
    const signature = updateNoticeSignature(updateStatus);

    expect(shouldShowUpdateNotice(updateStatus, "")).toBe(true);
    expect(shouldShowUpdateNotice(updateStatus, signature)).toBe(false);
    expect(shouldShowUpdateNotice({ ...updateStatus, latest_version: "0.18.0" }, signature)).toBe(true);
  });

  it("does not render for up-to-date status", () => {
    const html = renderToStaticMarkup(
      <UpdateNotice
        updateStatus={{ ...updateStatus, state: "up_to_date" }}
        dismissedSignature=""
        onDismiss={vi.fn()}
      />,
    );

    expect(html).toBe("");
  });
});
