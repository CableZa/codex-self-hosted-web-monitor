import type { SessionHistoryReport, SessionProjectRow, SessionSummary, Snapshot } from "./apiTypes";
import { hasVisibleContextSignal, sessionSignalThresholds, type SessionSignalThresholds } from "./sessionSignalThresholds";

export type SignalSeverity = "critical" | "warning" | "info" | "ok";

export type WeeklyRunway = {
  budgetCredits: number;
  currentCredits: number;
  creditsLeft: number;
  elapsedDays: number;
  remainingDays: number;
  safeDailySpend: number;
  spendRateVsTarget: number;
  projectedExhaustionDate: string | null;
  projectedExhaustionLabel: string;
  severity: SignalSeverity;
};

export type BurnAdvisory = {
  id: string;
  severity: Exclude<SignalSeverity, "ok">;
  message: string;
  label: string;
  value: string;
};

export type SessionWasteReasonId =
  | "low-cache"
  | "huge-uncached"
  | "long-context"
  | "high-output"
  | "repeated-project"
  | "output-waste"
  | "retry-churn"
  | "tool-cascade"
  | "looping"
  | "bad-decomposition"
  | "web-overhead"
  | "large-ingest"
  | "right-sizing";

export type SessionWasteReason = {
  id: SessionWasteReasonId;
  label: string;
  action: string;
};

export type SessionWasteFinding = {
  session: SessionSummary;
  score: number;
  reasons: SessionWasteReason[];
};

export type ProjectWasteRollup = {
  project: string;
  projectPath?: string | null;
  sessions: number;
  totalCredits: number;
  wasteCredits: number;
  score: number;
  reasons: SessionWasteReason[];
  topSession?: SessionSummary;
};

export const sessionWasteReasonOptions: SessionWasteReason[] = [
  { id: "low-cache", label: "Low cache reuse", action: "start a fresh session" },
  { id: "huge-uncached", label: "Huge uncached input", action: "split task" },
  { id: "long-context", label: "Long context", action: "avoid broad repo context" },
  { id: "high-output", label: "High output", action: "ask for concise output" },
  { id: "repeated-project", label: "Repeated expensive project", action: "break work into focused sessions" },
  { id: "output-waste", label: "Output waste", action: "ask for concise output" },
  { id: "retry-churn", label: "Retry churn", action: "inspect the first failure" },
  { id: "tool-cascade", label: "Tool cascade", action: "fix tool errors first" },
  { id: "looping", label: "Looping", action: "change approach" },
  { id: "bad-decomposition", label: "Large prompt", action: "split task" },
  { id: "web-overhead", label: "Web overhead", action: "use focused source checks" },
  { id: "large-ingest", label: "Large ingest", action: "summarize once" },
  { id: "right-sizing", label: "Right-sizing", action: "lower effort for small tasks" },
];

const sessionWasteReasonsById = new Map(sessionWasteReasonOptions.map((reason) => [reason.id, reason]));
const dayMs = 86_400_000;
const repeatedProjectSessions = 3;

function numberValue(value: unknown) {
  return typeof value === "number" && Number.isFinite(value) ? value : Number(value || 0);
}

function utcDate(day: string) {
  const [year, month, date] = day.split("-").map(Number);
  return new Date(Date.UTC(year, month - 1, date));
}

function utcNoonDate(day: string) {
  const [year, month, date] = day.split("-").map(Number);
  return new Date(Date.UTC(year, month - 1, date, 12));
}

function addDays(day: string, days: number) {
  return new Date(utcDate(day).getTime() + days * dayMs).toISOString().slice(0, 10);
}

function daysBetween(start: string, end: string) {
  return Math.round((utcDate(end).getTime() - utcDate(start).getTime()) / dayMs);
}

function dayInTimeZone(value: string, timeZone: string) {
  const parts = new Intl.DateTimeFormat("en-GB", {
    timeZone,
    year: "numeric",
    month: "2-digit",
    day: "2-digit",
  }).formatToParts(new Date(value));
  const values = Object.fromEntries(parts.map((part) => [part.type, part.value]));
  return `${values.year}-${values.month}-${values.day}`;
}

function weekdayLabel(day: string, timeZone: string) {
  return new Intl.DateTimeFormat("en-ZA", { weekday: "long", timeZone }).format(utcNoonDate(day));
}

function weekBudget(snapshot?: Snapshot) {
  return snapshot?.budgets?.find((budget) => budget.period === "week");
}

function todayBudget(snapshot?: Snapshot) {
  return snapshot?.budgets?.find((budget) => budget.period === "today");
}

export function weeklyCreditRunway(snapshot?: Snapshot): WeeklyRunway | null {
  const budget = weekBudget(snapshot);
  if (!snapshot || !budget || numberValue(budget.budget_credits) <= 0) return null;

  const budgetCredits = numberValue(budget.budget_credits);
  const currentCredits = numberValue(budget.current_credits);
  const weekStart = budget.start;
  const weekEnd = addDays(weekStart, 6);
  const timeZone = snapshot.timezone || "UTC";
  const today = dayInTimeZone(snapshot.generated_at, timeZone);
  const elapsedDays = Math.min(Math.max(daysBetween(weekStart, today) + 1, 1), 7);
  const remainingDays = Math.max(daysBetween(today, weekEnd) + 1, 0);
  const creditsLeft = Math.max(budgetCredits - currentCredits, 0);
  const safeDailySpend = remainingDays > 0 ? creditsLeft / remainingDays : 0;
  const targetToDate = budgetCredits * (elapsedDays / 7);
  const spendRateVsTarget = targetToDate > 0 ? currentCredits / targetToDate : 0;
  const averageDailySpend = elapsedDays > 0 ? currentCredits / elapsedDays : 0;
  let projectedExhaustionDate: string | null = null;
  let projectedExhaustionLabel = "Not projected this week";

  if (budgetCredits > 0 && averageDailySpend > 0 && currentCredits >= budgetCredits) {
    projectedExhaustionDate = today;
    projectedExhaustionLabel = "Already exhausted";
  } else if (budgetCredits > 0 && averageDailySpend > 0) {
    const daysUntilExhaustion = Math.ceil((budgetCredits - currentCredits) / averageDailySpend);
    const projected = addDays(today, Math.max(daysUntilExhaustion, 0));
    if (projected <= weekEnd) {
      projectedExhaustionDate = projected;
      projectedExhaustionLabel = weekdayLabel(projected, timeZone);
    }
  }

  const severity: SignalSeverity = currentCredits >= budgetCredits
    ? "critical"
    : projectedExhaustionDate
      ? "warning"
      : spendRateVsTarget > 1.1
        ? "info"
        : "ok";

  return {
    budgetCredits,
    currentCredits,
    creditsLeft,
    elapsedDays,
    remainingDays,
    safeDailySpend,
    spendRateVsTarget,
    projectedExhaustionDate,
    projectedExhaustionLabel,
    severity,
  };
}

export function burnAdvisories(snapshot?: Snapshot): BurnAdvisory[] {
  const runway = weeklyCreditRunway(snapshot);
  const weeklyBudget = weekBudget(snapshot);
  if (!snapshot || !runway || !weeklyBudget || runway.budgetCredits <= 0) return [];

  const todayCredits = numberValue(todayBudget(snapshot)?.current_credits);
  const dailyTarget = runway.budgetCredits / 7;
  const todayVsTarget = dailyTarget > 0 ? todayCredits / dailyTarget : 0;
  const timeZone = snapshot.timezone || "UTC";
  const advisories: BurnAdvisory[] = [];

  if (runway.currentCredits >= runway.budgetCredits) {
    advisories.push({
      id: "week-exhausted",
      severity: "critical",
      message: "Weekly credit budget is already exhausted.",
      label: "Remaining",
      value: "0 credits",
    });
  } else if (runway.projectedExhaustionDate) {
    advisories.push({
      id: "projected-exhaustion",
      severity: runway.projectedExhaustionDate <= dayInTimeZone(snapshot.generated_at, timeZone) ? "critical" : "warning",
      message: `At current pace you will run out by ${runway.projectedExhaustionLabel}.`,
      label: "Projected",
      value: runway.projectedExhaustionLabel,
    });
  }

  if (todayVsTarget >= 1.5) {
    advisories.push({
      id: "today-over-target",
      severity: todayVsTarget >= 2 ? "critical" : "warning",
      message: `Today's usage is ${todayVsTarget.toFixed(1)}x target.`,
      label: "Today pace",
      value: `${todayVsTarget.toFixed(1)}x`,
    });
  } else if (todayVsTarget > 1.1) {
    advisories.push({
      id: "today-above-target",
      severity: "info",
      message: `Today's usage is ${todayVsTarget.toFixed(1)}x target.`,
      label: "Today pace",
      value: `${todayVsTarget.toFixed(1)}x`,
    });
  }

  if (runway.remainingDays >= 2 && runway.creditsLeft > 0 && runway.safeDailySpend < dailyTarget * 0.75) {
    advisories.push({
      id: "thin-runway",
      severity: runway.safeDailySpend < dailyTarget * 0.4 ? "critical" : "warning",
      message: `${Math.round(runway.creditsLeft)} credits left across ${runway.remainingDays} days.`,
      label: "Safe daily pace",
      value: `${Math.round(runway.safeDailySpend)} credits/day`,
    });
  }

  if (!advisories.length && runway.spendRateVsTarget > 1.1) {
    advisories.push({
      id: "week-above-target",
      severity: "info",
      message: `Weekly spend is ${runway.spendRateVsTarget.toFixed(1)}x the target pace.`,
      label: "Week pace",
      value: `${runway.spendRateVsTarget.toFixed(1)}x`,
    });
  }

  return advisories.slice(0, 3);
}

function projectCreditThreshold(sessions?: SessionHistoryReport) {
  const totals = numberValue(sessions?.totals.total_credits);
  return Math.max(totals * 0.2, 100);
}

function projectKey(project?: string | null, projectPath?: string | null) {
  return `${project || ""}\u0000${projectPath || ""}`;
}

function reason(id: SessionWasteReasonId) {
  return sessionWasteReasonsById.get(id) || sessionWasteReasonOptions[0];
}

function backendReasons(session: SessionSummary): SessionWasteReason[] {
  return (session.waste_findings || []).map((finding) => ({
    id: finding.id as SessionWasteReasonId,
    label: finding.label,
    action: finding.recommendation,
  }));
}

function projectRowsByKey(sessions?: SessionHistoryReport) {
  return new Map((sessions?.by_project || []).map((project) => [projectKey(project.project, project.project_path), project]));
}

function findProjectRow(
  session: SessionSummary,
  projects: Map<string, SessionProjectRow>,
) {
  return session.project_name ? projects.get(projectKey(session.project_name, session.project_path)) : undefined;
}

export function sessionWasteScore(
  session: SessionSummary,
  sessions?: SessionHistoryReport,
  thresholds: SessionSignalThresholds = sessionSignalThresholds(),
) {
  const projects = projectRowsByKey(sessions);
  const projectThreshold = projectCreditThreshold(sessions);
  const reasons: SessionWasteReason[] = backendReasons(session);
  const hasBackendReasons = reasons.length > 0;
  const cacheRatio = numberValue(session.cache_efficiency ?? session.cache_hit_ratio);
  const uncachedInput = numberValue(session.uncached_input_tokens);
  const outputTokens = numberValue(session.output_tokens);
  const project = findProjectRow(session, projects);

  if (!hasBackendReasons && cacheRatio <= thresholds.lowCacheMaxReuseRatio && uncachedInput >= thresholds.lowCacheMinUncachedTokens) {
    reasons.push(reason("low-cache"));
  }
  if (!hasBackendReasons && uncachedInput >= thresholds.highUncachedInputTokens) {
    reasons.push(reason("huge-uncached"));
  }
  if (!hasBackendReasons && hasVisibleContextSignal(session, thresholds)) {
    reasons.push(reason("long-context"));
  }
  if (!hasBackendReasons && outputTokens >= thresholds.highOutputTokens) {
    reasons.push(reason("high-output"));
  }
  if (!hasBackendReasons && project && numberValue(project.sessions) >= repeatedProjectSessions && numberValue(project.total_credits) >= projectThreshold) {
    reasons.push(reason("repeated-project"));
  }

  const score = numberValue(session.total_credits) + reasons.length * 50 + uncachedInput / 10_000 + outputTokens / 10_000 + numberValue(session.estimated_waste_credits);
  return { session, score, reasons };
}

export function sessionWasteFindings(
  sessions?: SessionHistoryReport,
  visibleSessions?: SessionSummary[],
  options?: { reasonId?: SessionWasteReasonId | ""; limit?: number; thresholds?: SessionSignalThresholds },
) {
  const rows = visibleSessions || sessions?.sessions || [];
  const reasonId = options?.reasonId || "";
  const limit = options?.limit ?? 6;

  const thresholds = options?.thresholds || sessionSignalThresholds();
  const findings = rows.map((session) => sessionWasteScore(session, sessions, thresholds))
    .filter((finding): finding is SessionWasteFinding => {
      if (!finding.reasons.length) return false;
      if (!reasonId) return true;
      return finding.reasons.some((item) => item.id === reasonId);
    })
    .sort((left, right) => right.score - left.score);

  return limit > 0 ? findings.slice(0, limit) : findings;
}

export function projectWasteRollups(sessions?: SessionHistoryReport, visibleSessions?: SessionSummary[], thresholds?: SessionSignalThresholds) {
  const findings = sessionWasteFindings(sessions, visibleSessions, { limit: 0, thresholds });
  const rollups = new Map<string, ProjectWasteRollup>();
  const projectTotals = projectRowsByKey(sessions);

  for (const finding of findings) {
    const session = finding.session;
    const project = session.project_name || "Unknown project";
    const key = projectKey(project, session.project_path);
    const projectTotal = projectTotals.get(key);
    const existing = rollups.get(key) || {
      project,
      projectPath: session.project_path,
      sessions: 0,
      totalCredits: numberValue(projectTotal?.total_credits),
      wasteCredits: 0,
      score: 0,
      reasons: [],
      topSession: session,
    };
    const reasonIds = new Set(existing.reasons.map((item) => item.id));
    existing.sessions += 1;
    existing.wasteCredits += numberValue(session.total_credits);
    existing.score += finding.score;
    if (!existing.totalCredits) existing.totalCredits += numberValue(session.total_credits);
    if (numberValue(session.total_credits) > numberValue(existing.topSession?.total_credits)) existing.topSession = session;
    for (const findingReason of finding.reasons) {
      if (!reasonIds.has(findingReason.id)) {
        existing.reasons.push(findingReason);
        reasonIds.add(findingReason.id);
      }
    }
    rollups.set(key, existing);
  }

  return [...rollups.values()].sort((left, right) => right.score - left.score);
}

export function sessionMatchesWasteReason(
  session: SessionSummary,
  sessions?: SessionHistoryReport,
  reasonId?: SessionWasteReasonId | "",
  thresholds?: SessionSignalThresholds,
) {
  if (!reasonId) return true;
  return sessionWasteScore(session, sessions, thresholds).reasons.some((item) => item.id === reasonId);
}

export function safeDailySpendForChart(snapshot?: Snapshot) {
  const runway = weeklyCreditRunway(snapshot);
  if (!runway || runway.safeDailySpend <= 0) return null;
  return runway.safeDailySpend;
}

export function weeklyBudgetWindow(snapshot?: Snapshot) {
  const budget = weekBudget(snapshot);
  if (!budget || numberValue(budget.budget_credits) <= 0) return null;
  return { start: budget.start, end: addDays(budget.start, 6) };
}
