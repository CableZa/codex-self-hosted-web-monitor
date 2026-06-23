import type { SessionSummary, Settings } from "./apiTypes";
import { fmtCompactNum } from "./format";

export type SessionSignalThresholds = {
  highInputTokens: number;
  highUncachedInputTokens: number;
  lowCacheMinUncachedTokens: number;
  lowCacheMaxReuseRatio: number;
  largeTotalTokens: number;
  highOutputTokens: number;
  longContextPricingSignalEnabled: boolean;
};

export const defaultSessionSignalThresholdSettings = {
  session_high_input_tokens: "1000000",
  session_high_uncached_input_tokens: "250000",
  session_low_cache_min_uncached_tokens: "100000",
  session_low_cache_max_reuse_ratio: "0.5",
  session_large_total_tokens: "1500000",
  session_high_output_tokens: "100000",
  session_long_context_pricing_signal_enabled: "true",
};

const defaultThresholds: SessionSignalThresholds = {
  highInputTokens: 1_000_000,
  highUncachedInputTokens: 250_000,
  lowCacheMinUncachedTokens: 100_000,
  lowCacheMaxReuseRatio: 0.5,
  largeTotalTokens: 1_500_000,
  highOutputTokens: 100_000,
  longContextPricingSignalEnabled: true,
};

function positiveInt(value: unknown, fallback: number) {
  const number = Number(value);
  return Number.isFinite(number) && number > 0 ? Math.trunc(number) : fallback;
}

function ratio(value: unknown, fallback: number) {
  const number = Number(value);
  return Number.isFinite(number) && number >= 0 && number <= 1 ? number : fallback;
}

function boolValue(value: unknown, fallback: boolean) {
  const normalized = String(value ?? "").trim().toLowerCase();
  if (["1", "true", "yes", "on"].includes(normalized)) return true;
  if (["0", "false", "no", "off"].includes(normalized)) return false;
  return fallback;
}

export function sessionSignalThresholds(settings?: Partial<Settings>): SessionSignalThresholds {
  return {
    highInputTokens: positiveInt(settings?.session_high_input_tokens, defaultThresholds.highInputTokens),
    highUncachedInputTokens: positiveInt(settings?.session_high_uncached_input_tokens, defaultThresholds.highUncachedInputTokens),
    lowCacheMinUncachedTokens: positiveInt(settings?.session_low_cache_min_uncached_tokens, defaultThresholds.lowCacheMinUncachedTokens),
    lowCacheMaxReuseRatio: ratio(settings?.session_low_cache_max_reuse_ratio, defaultThresholds.lowCacheMaxReuseRatio),
    largeTotalTokens: positiveInt(settings?.session_large_total_tokens, defaultThresholds.largeTotalTokens),
    highOutputTokens: positiveInt(settings?.session_high_output_tokens, defaultThresholds.highOutputTokens),
    longContextPricingSignalEnabled: boolValue(
      settings?.session_long_context_pricing_signal_enabled,
      defaultThresholds.longContextPricingSignalEnabled,
    ),
  };
}

export function signalDescriptions(thresholds: SessionSignalThresholds = defaultThresholds): Record<string, string> {
  return {
    "high input volume": `Session input tokens are at least ${fmtCompactNum.format(thresholds.highInputTokens)}. This flags very large prompts, file context, or repeated context injection.`,
    "high uncached input": `Uncached input tokens are at least ${fmtCompactNum.format(thresholds.highUncachedInputTokens)}. These tokens are usually more expensive than cached input and often explain high credit use.`,
    "low cache reuse": `At least ${fmtCompactNum.format(thresholds.lowCacheMinUncachedTokens)} input tokens were uncached and input cache reuse was at most ${Math.round(thresholds.lowCacheMaxReuseRatio * 100)}%.`,
    "large token footprint": `Total session tokens are at least ${fmtCompactNum.format(thresholds.largeTotalTokens)} across input, cached input, output, and reasoning output.`,
    "high output volume": `Output tokens are at least ${fmtCompactNum.format(thresholds.highOutputTokens)}. This can happen with very long generated code, logs, or repeated retries.`,
    "long-context pricing": thresholds.longContextPricingSignalEnabled
      ? "The local price metadata marked one or more events as long-context pricing. This affects secondary USD diagnostics, not Codex credits."
      : "Long-context pricing is hidden as a visible signal in Settings.",
  };
}

export function signalDescription(reason: string, thresholds?: SessionSignalThresholds) {
  return signalDescriptions(thresholds)[reason] || "Session context signal.";
}

export function hasVisibleContextSignal(session: SessionSummary, thresholds: SessionSignalThresholds) {
  if (session.long_context_reasons?.some((reason) => reason !== "long-context pricing")) return true;
  if (session.long_context_reasons?.includes("long-context pricing")) return thresholds.longContextPricingSignalEnabled;
  return Boolean(session.long_context && (thresholds.longContextPricingSignalEnabled || !session.long_context_applied))
    || Boolean(thresholds.longContextPricingSignalEnabled && (session.long_context_applied || Number(session.long_context_events || 0) > 0));
}

export function visibleContextReasons(session: SessionSummary, thresholds: SessionSignalThresholds) {
  return (session.long_context_reasons || []).filter((reason) => reason !== "long-context pricing" || thresholds.longContextPricingSignalEnabled);
}

export function thresholdsEqualSettings(left: Partial<Settings>, right: Partial<Settings>) {
  return Object.keys(defaultSessionSignalThresholdSettings).every((key) => String(left[key as keyof Settings] || "") === String(right[key as keyof Settings] || ""));
}
