from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

from codex_usage_models import CostBreakdown, TokenUsage


def load_prices(path: Path) -> dict[str, Any]:
    with path.expanduser().open("r", encoding="utf-8") as handle:
        data = json.load(handle)
    if "models" not in data or not isinstance(data["models"], dict):
        raise ValueError(f"{path} must contain a top-level 'models' object")
    return data


SNAPSHOT_SUFFIX_RE = re.compile(r"-\d{4}-\d{2}-\d{2}$")


def lookup_rates(model: str, prices: dict[str, Any]) -> tuple[str | None, dict[str, Any] | None]:
    models = prices["models"]
    aliases = prices.get("aliases", {})
    if not isinstance(aliases, dict):
        aliases = {}
    candidates = [model]
    if model in aliases:
        candidates.append(aliases[model])

    stripped = SNAPSHOT_SUFFIX_RE.sub("", model)
    if stripped != model:
        candidates.append(stripped)
        if stripped in aliases:
            candidates.append(aliases[stripped])

    for candidate in candidates:
        rates = models.get(candidate)
        if isinstance(rates, dict):
            return candidate, rates
    return None, None


def cost_for_usage(usage: TokenUsage, rates: dict[str, Any]) -> CostBreakdown:
    input_rate = float(rates["input"])
    cached_rate = float(rates.get("cached_input", input_rate) or input_rate)
    output_rate = float(rates["output"])
    reasoning_rate = float(rates.get("reasoning_output", output_rate) or output_rate)
    input_credit_rate = float(rates.get("input_credits", input_rate * 25))
    cached_credit_rate = float(rates.get("cached_input_credits", cached_rate * 25) or cached_rate * 25)
    output_credit_rate = float(rates.get("output_credits", output_rate * 25))
    reasoning_credit_rate = float(rates.get("reasoning_output_credits", output_credit_rate) or output_credit_rate)

    input_multiplier = 1.0
    output_multiplier = 1.0
    long_context_applied = False
    long_context = rates.get("long_context")
    if isinstance(long_context, dict):
        threshold = int(long_context.get("input_threshold", 0) or 0)
        if threshold and usage.input_tokens > threshold:
            input_multiplier = float(long_context.get("input_multiplier", 1.0) or 1.0)
            output_multiplier = float(long_context.get("output_multiplier", 1.0) or 1.0)
            long_context_applied = True

    cached_tokens = min(usage.cached_input_tokens, usage.input_tokens)
    uncached_tokens = max(usage.input_tokens - cached_tokens, 0)
    reasoning_extra_tokens = max(usage.total_tokens - usage.input_tokens - usage.output_tokens, 0)
    reasoning_extra_tokens = min(reasoning_extra_tokens, usage.reasoning_output_tokens)

    input_usd = uncached_tokens * input_rate * input_multiplier / 1_000_000
    cached_input_usd = cached_tokens * cached_rate * input_multiplier / 1_000_000
    output_usd = usage.output_tokens * output_rate * output_multiplier / 1_000_000
    reasoning_output_usd = reasoning_extra_tokens * reasoning_rate * output_multiplier / 1_000_000
    input_credits = uncached_tokens * input_credit_rate / 1_000_000
    cached_input_credits = cached_tokens * cached_credit_rate / 1_000_000
    output_credits = usage.output_tokens * output_credit_rate / 1_000_000
    reasoning_output_credits = reasoning_extra_tokens * reasoning_credit_rate / 1_000_000

    return CostBreakdown(
        input_usd=input_usd,
        cached_input_usd=cached_input_usd,
        output_usd=output_usd,
        reasoning_output_usd=reasoning_output_usd,
        total_usd=input_usd + cached_input_usd + output_usd + reasoning_output_usd,
        input_credits=input_credits,
        cached_input_credits=cached_input_credits,
        output_credits=output_credits,
        reasoning_output_credits=reasoning_output_credits,
        total_credits=input_credits + cached_input_credits + output_credits + reasoning_output_credits,
        long_context_applied=long_context_applied,
    )
