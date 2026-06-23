import type { SessionHistoryReport, SessionSummary } from "./apiTypes";
import { sessionWasteScore } from "./dashboardSignals";
import { signalDescription as thresholdSignalDescription, signalDescriptions as thresholdSignalDescriptions, type SessionSignalThresholds } from "./sessionSignalThresholds";

export function formatDuration(seconds: number) {
  if (seconds <= 0) return "0s";
  const hours = Math.floor(seconds / 3600);
  const minutes = Math.floor((seconds % 3600) / 60);
  const remainingSeconds = seconds % 60;
  if (hours > 0) return `${hours}h ${String(minutes).padStart(2, "0")}m`;
  if (minutes > 0) return `${minutes}m ${String(remainingSeconds).padStart(2, "0")}s`;
  return `${remainingSeconds}s`;
}

export function formatPercent(value: number) {
  return `${Math.round(value * 100)}%`;
}

export const signalDescriptions = thresholdSignalDescriptions();

export function signalDescription(reason: string, thresholds?: SessionSignalThresholds) {
  return thresholdSignalDescription(reason, thresholds);
}

export function sortSessions(sessions: SessionSummary[], sortMode: string, history?: SessionHistoryReport, thresholds?: SessionSignalThresholds) {
  const rows = [...sessions];
  rows.sort((left, right) => {
    if (sortMode === "waste") {
      const leftWaste = sessionWasteScore(left, history, thresholds);
      const rightWaste = sessionWasteScore(right, history, thresholds);
      const leftScore = leftWaste.reasons.length ? leftWaste.score : -1;
      const rightScore = rightWaste.reasons.length ? rightWaste.score : -1;
      return rightScore - leftScore;
    }
    if (sortMode === "tokens") return (right.total_tokens || 0) - (left.total_tokens || 0);
    if (sortMode === "uncached") return (right.uncached_input_tokens || 0) - (left.uncached_input_tokens || 0);
    if (sortMode === "cache") return (left.cache_efficiency || left.cache_hit_ratio || 0) - (right.cache_efficiency || right.cache_hit_ratio || 0);
    if (sortMode === "duration") return (right.duration_seconds || 0) - (left.duration_seconds || 0);
    if (sortMode === "oldest") return String(left.first_seen || "").localeCompare(String(right.first_seen || ""));
    if (sortMode === "recent") return String(right.last_seen || "").localeCompare(String(left.last_seen || ""));
    return (right.total_credits || 0) - (left.total_credits || 0);
  });
  return rows;
}

export function sessionSearchText(session: SessionSummary) {
  return [
    session.session_id,
    session.display_title,
    session.first_message,
    session.last_message,
    session.summary,
    session.project_name,
    session.project_path,
    ...session.accounts,
    ...session.by_model.map((row) => row.model),
  ].filter(Boolean).join(" ").toLowerCase();
}
