from __future__ import annotations

from typing import Any

from .session_signals import SessionSignalThresholds, session_signal_thresholds

EFFORT_HIGH_VALUES = {"high", "xhigh", "extra-high", "extra_high"}


def number_value(value: Any) -> float:
    try:
        return float(value or 0)
    except (TypeError, ValueError):
        return 0.0


def finding(
    session: dict[str, Any],
    finding_id: str,
    severity: str,
    label: str,
    recommendation: str,
    confidence: str,
    evidence: str,
    factor: float,
) -> dict[str, Any]:
    return {
        "id": finding_id,
        "severity": severity,
        "label": label,
        "recommendation": recommendation,
        "confidence": confidence,
        "evidence": evidence,
        "estimated_waste_credits": round(number_value(session.get("total_credits")) * factor, 4),
        "estimated_waste_usd": round(number_value(session.get("total_usd")) * factor, 4),
    }


def scale_estimates(session: dict[str, Any], findings: list[dict[str, Any]]) -> None:
    max_credits = number_value(session.get("total_credits")) * 0.75
    max_usd = number_value(session.get("total_usd")) * 0.75
    total_credits = sum(number_value(item.get("estimated_waste_credits")) for item in findings)
    total_usd = sum(number_value(item.get("estimated_waste_usd")) for item in findings)
    credit_scale = min(max_credits / total_credits, 1) if total_credits > 0 else 1
    usd_scale = min(max_usd / total_usd, 1) if total_usd > 0 else 1
    for item in findings:
        item["estimated_waste_credits"] = round(number_value(item.get("estimated_waste_credits")) * credit_scale, 4)
        item["estimated_waste_usd"] = round(number_value(item.get("estimated_waste_usd")) * usd_scale, 4)


def efficiency_grade(score: int) -> str:
    if score >= 92:
        return "S"
    if score >= 82:
        return "A"
    if score >= 70:
        return "B"
    if score >= 55:
        return "C"
    if score >= 40:
        return "D"
    return "F"


def session_waste_findings(session: dict[str, Any], thresholds: SessionSignalThresholds | None = None) -> list[dict[str, Any]]:
    active = thresholds or session_signal_thresholds()
    findings: list[dict[str, Any]] = []
    uncached_input = number_value(session.get("uncached_input_tokens"))
    output_tokens = number_value(session.get("output_tokens"))
    total_tokens = number_value(session.get("total_tokens"))
    total_credits = number_value(session.get("total_credits"))
    cache_efficiency = number_value(session.get("cache_efficiency") or session.get("cache_hit_ratio"))
    first_words = int(session.get("first_message_word_count") or 0)
    tool_errors = int(session.get("tool_error_count") or 0)
    repeated_tools = int(session.get("repeated_tool_signatures") or 0)
    web_tools = int(session.get("web_tool_call_count") or 0)
    max_error_run = int(session.get("max_consecutive_tool_errors") or 0)
    large_ingests = int(session.get("large_ingest_count") or 0)
    effort_values = {str(item or "").lower() for item in session.get("efforts", [])}
    effort_values.add(str(session.get("effort") or "").lower())
    model_efforts = {str(row.get("model") or "").lower() for row in session.get("by_model", []) if isinstance(row, dict)}
    high_effort = bool(effort_values & EFFORT_HIGH_VALUES) or any("xhigh" in item for item in model_efforts)

    if cache_efficiency <= active.low_cache_max_reuse_ratio and uncached_input >= active.low_cache_min_uncached_tokens:
        findings.append(finding(session, "low-cache", "warning", "Low cache reuse", "Start a fresh, focused session or trim context before continuing.", "high", f"{int(uncached_input):,} uncached input tokens with {cache_efficiency:.0%} cache reuse.", 0.2))
    if uncached_input >= active.high_uncached_input_tokens:
        findings.append(finding(session, "huge-uncached", "warning", "Huge uncached input", "Split broad work into smaller sessions and avoid repeatedly loading the same repo context.", "high", f"{int(uncached_input):,} uncached input tokens.", 0.25))
    if output_tokens >= active.high_output_tokens:
        findings.append(finding(session, "output-waste", "info", "High output volume", "Ask for concise output when you only need a patch or summary.", "high", f"{int(output_tokens):,} output tokens.", 0.12))
    if repeated_tools:
        findings.append(finding(session, "retry-churn", "warning", "Repeated tool retries", "Stop after repeated failures and inspect the first error before retrying.", "medium", f"{repeated_tools} repeated tool signature cluster(s).", 0.15))
    if max_error_run >= 4:
        findings.append(finding(session, "tool-cascade", "warning", "Tool error cascade", "Resolve the tool failure before continuing the task.", "medium", f"{max_error_run} consecutive tool errors.", 0.2))
    if repeated_tools and tool_errors >= 5:
        findings.append(finding(session, "looping", "critical", "Looping tool pattern", "Pause and change approach when the same operation keeps failing.", "medium", f"{tool_errors} tool errors and repeated tool signatures.", 0.25))
    if first_words >= 800:
        findings.append(finding(session, "bad-decomposition", "info", "Large starting prompt", "Break large asks into staged tasks with clear checkpoints.", "medium", f"First prompt is about {first_words:,} words.", 0.1))
    if web_tools >= 8 and total_credits >= 10:
        findings.append(finding(session, "web-overhead", "info", "Heavy web/tool overhead", "Use focused source checks instead of broad search/fetch loops.", "medium", f"{web_tools} web or fetch-like tool calls.", 0.1))
    if large_ingests and uncached_input >= 75_000:
        findings.append(finding(session, "large-ingest", "warning", "Large content ingestion", "Summarize large documents once and reuse the summary.", "medium", f"{large_ingests} large ingest signal(s) with {int(uncached_input):,} uncached input tokens.", 0.2))
    if high_effort and total_tokens < 100_000 and not session.get("long_context"):
        findings.append(finding(session, "right-sizing", "info", "Model or effort right-sizing", "Use lower reasoning effort for small read-only or simple edit sessions.", "low", f"{int(total_tokens):,} total tokens with high effort signal.", 0.08))

    scale_estimates(session, findings)
    return findings


def add_waste_fields(session: dict[str, Any], thresholds: SessionSignalThresholds | None = None) -> dict[str, Any]:
    findings = session_waste_findings(session, thresholds)
    estimated_credits = round(sum(number_value(item.get("estimated_waste_credits")) for item in findings), 4)
    estimated_usd = round(sum(number_value(item.get("estimated_waste_usd")) for item in findings), 4)
    penalty = min(estimated_credits / max(number_value(session.get("total_credits")), 1), 1) * 65 + min(len(findings) * 4, 20)
    score = max(0, min(100, round(100 - penalty)))
    session["waste_findings"] = findings
    session["estimated_waste_credits"] = estimated_credits
    session["estimated_waste_usd"] = estimated_usd
    session["efficiency_score"] = score
    session["efficiency_grade"] = efficiency_grade(score)
    return session
