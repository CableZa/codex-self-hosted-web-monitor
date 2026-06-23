from __future__ import annotations

from dataclasses import dataclass


SESSION_SIGNAL_THRESHOLD_DEFAULTS = {
    "session_high_input_tokens": "1000000",
    "session_high_uncached_input_tokens": "250000",
    "session_low_cache_min_uncached_tokens": "100000",
    "session_low_cache_max_reuse_ratio": "0.5",
    "session_large_total_tokens": "1500000",
    "session_high_output_tokens": "100000",
    "session_long_context_pricing_signal_enabled": "true",
}
SESSION_SIGNAL_THRESHOLD_KEYS = frozenset(SESSION_SIGNAL_THRESHOLD_DEFAULTS)


@dataclass(frozen=True)
class SessionSignalThresholds:
    high_input_tokens: int = 1_000_000
    high_uncached_input_tokens: int = 250_000
    low_cache_min_uncached_tokens: int = 100_000
    low_cache_max_reuse_ratio: float = 0.5
    large_total_tokens: int = 1_500_000
    high_output_tokens: int = 100_000
    long_context_pricing_signal_enabled: bool = True


def _int_setting(settings: dict[str, str], key: str, default: int) -> int:
    try:
        value = int(float(str(settings.get(key, default)).strip()))
    except (TypeError, ValueError):
        return default
    return value if value > 0 else default


def _ratio_setting(settings: dict[str, str], key: str, default: float) -> float:
    try:
        value = float(str(settings.get(key, default)).strip())
    except (TypeError, ValueError):
        return default
    return value if 0 <= value <= 1 else default


def _bool_setting(settings: dict[str, str], key: str, default: bool) -> bool:
    value = str(settings.get(key, str(default))).strip().lower()
    if value in {"1", "true", "yes", "on"}:
        return True
    if value in {"0", "false", "no", "off"}:
        return False
    return default


def session_signal_thresholds(settings: dict[str, str] | None = None) -> SessionSignalThresholds:
    values = settings or {}
    defaults = SessionSignalThresholds()
    return SessionSignalThresholds(
        high_input_tokens=_int_setting(values, "session_high_input_tokens", defaults.high_input_tokens),
        high_uncached_input_tokens=_int_setting(values, "session_high_uncached_input_tokens", defaults.high_uncached_input_tokens),
        low_cache_min_uncached_tokens=_int_setting(values, "session_low_cache_min_uncached_tokens", defaults.low_cache_min_uncached_tokens),
        low_cache_max_reuse_ratio=_ratio_setting(values, "session_low_cache_max_reuse_ratio", defaults.low_cache_max_reuse_ratio),
        large_total_tokens=_int_setting(values, "session_large_total_tokens", defaults.large_total_tokens),
        high_output_tokens=_int_setting(values, "session_high_output_tokens", defaults.high_output_tokens),
        long_context_pricing_signal_enabled=_bool_setting(values, "session_long_context_pricing_signal_enabled", defaults.long_context_pricing_signal_enabled),
    )
