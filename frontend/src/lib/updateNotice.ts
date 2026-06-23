import type { UpdateStatus } from "./apiTypes";

export function updateNoticeSignature(updateStatus?: UpdateStatus | null) {
  if (!updateStatus || updateStatus.state !== "update_available") return "";
  return [updateStatus.latest_version || "", updateStatus.latest_tag || "", updateStatus.message || ""].join("|");
}

export function shouldShowUpdateNotice(updateStatus: UpdateStatus | undefined, dismissedSignature: string) {
  const signature = updateNoticeSignature(updateStatus);
  return Boolean(signature && signature !== dismissedSignature);
}
