from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

from codex_usage_constants import TOKEN_FIELDS


TOKEN_ALIASES = {
    "input_tokens": ("input_tokens", "prompt_tokens", "input"),
    "cached_input_tokens": ("cached_input_tokens", "cache_read_input_tokens", "cached_tokens"),
    "output_tokens": ("output_tokens", "completion_tokens", "output"),
    "reasoning_output_tokens": ("reasoning_output_tokens", "reasoning_tokens"),
    "total_tokens": ("total_tokens",),
}


@dataclass
class TokenUsage:
    input_tokens: int = 0
    cached_input_tokens: int = 0
    output_tokens: int = 0
    reasoning_output_tokens: int = 0
    total_tokens: int = 0

    @classmethod
    def from_mapping(cls, data: dict[str, Any] | None) -> "TokenUsage":
        data = data or {}
        if not isinstance(data, dict):
            raise ValueError("usage must be an object")
        values: dict[str, int] = {}
        for field_name in TOKEN_FIELDS:
            value = 0
            for alias in TOKEN_ALIASES[field_name]:
                if alias in data:
                    value = data.get(alias, 0)
                    break
            try:
                values[field_name] = int(value or 0)
            except (TypeError, ValueError) as exc:
                raise ValueError(f"{field_name} must be an integer") from exc
        if values["total_tokens"] <= 0:
            values["total_tokens"] = values["input_tokens"] + values["output_tokens"] + values["reasoning_output_tokens"]
        return cls(**values)

    def is_zero(self) -> bool:
        return all(getattr(self, field_name) == 0 for field_name in TOKEN_FIELDS)

    def subtract(self, other: "TokenUsage | None") -> "TokenUsage":
        other = other or TokenUsage()
        return TokenUsage(
            **{
                field_name: max(getattr(self, field_name) - getattr(other, field_name), 0)
                for field_name in TOKEN_FIELDS
            }
        )

    @property
    def uncached_input_tokens(self) -> int:
        return max(self.input_tokens - min(self.cached_input_tokens, self.input_tokens), 0)

    def add(self, other: "TokenUsage") -> None:
        for field_name in TOKEN_FIELDS:
            setattr(self, field_name, getattr(self, field_name) + getattr(other, field_name))

    def as_dict(self) -> dict[str, int]:
        return {
            "input_tokens": self.input_tokens,
            "cached_input_tokens": self.cached_input_tokens,
            "uncached_input_tokens": self.uncached_input_tokens,
            "output_tokens": self.output_tokens,
            "reasoning_output_tokens": self.reasoning_output_tokens,
            "total_tokens": self.total_tokens,
        }


@dataclass
class CostBreakdown:
    input_usd: float = 0.0
    cached_input_usd: float = 0.0
    output_usd: float = 0.0
    reasoning_output_usd: float = 0.0
    total_usd: float = 0.0
    input_credits: float = 0.0
    cached_input_credits: float = 0.0
    output_credits: float = 0.0
    reasoning_output_credits: float = 0.0
    total_credits: float = 0.0
    long_context_applied: bool = False

    def add(self, other: "CostBreakdown") -> None:
        self.input_usd += other.input_usd
        self.cached_input_usd += other.cached_input_usd
        self.output_usd += other.output_usd
        self.reasoning_output_usd += other.reasoning_output_usd
        self.total_usd += other.total_usd
        self.input_credits += other.input_credits
        self.cached_input_credits += other.cached_input_credits
        self.output_credits += other.output_credits
        self.reasoning_output_credits += other.reasoning_output_credits
        self.total_credits += other.total_credits
        self.long_context_applied = self.long_context_applied or other.long_context_applied

    def as_dict(self) -> dict[str, Any]:
        return {
            "input_usd": round(self.input_usd, 8),
            "cached_input_usd": round(self.cached_input_usd, 8),
            "output_usd": round(self.output_usd, 8),
            "reasoning_output_usd": round(self.reasoning_output_usd, 8),
            "total_usd": round(self.total_usd, 8),
            "input_credits": round(self.input_credits, 8),
            "cached_input_credits": round(self.cached_input_credits, 8),
            "output_credits": round(self.output_credits, 8),
            "reasoning_output_credits": round(self.reasoning_output_credits, 8),
            "total_credits": round(self.total_credits, 8),
            "long_context_applied": self.long_context_applied,
        }


@dataclass
class UsageRecord:
    timestamp: datetime
    day: str
    model: str
    effort: str
    session_id: str
    path: str
    usage: TokenUsage
    account: str = "unknown"


@dataclass
class SessionMetadata:
    session_id: str
    first_message: str | None = None
    last_message: str | None = None
    project_path: str | None = None
    project_name: str | None = None
    user_message_count: int = 0
    first_message_word_count: int = 0
    tool_call_count: int = 0
    tool_error_count: int = 0
    max_consecutive_tool_errors: int = 0
    repeated_tool_signatures: int = 0
    web_tool_call_count: int = 0
    large_ingest_count: int = 0


@dataclass
class ParseDiagnostics:
    discovered_files: int = 0
    scanned_files: int = 0
    scan_bytes: int = 0
    usage_lines_scanned: int = 0
    usage_lines_prefiltered: int = 0
    metadata_lines_scanned: int = 0
    metadata_lines_prefiltered: int = 0
    json_decode_attempts: int = 0
    discovery_ms: int = 0
    usage_parse_ms: int = 0
    metadata_parse_ms: int = 0
    total_scan_ms: int = 0
    duplicate_files_skipped: int = 0
    invalid_json_events: int = 0
    non_object_json_events: int = 0
    non_object_payload_events: int = 0
    malformed_usage_events: int = 0
    zero_usage_events: int = 0
    cumulative_total_usage_events: int = 0
    last_token_usage_events: int = 0
    headless_usage_events: int = 0
    skipped_subagent_replay_events: int = 0
    usage_records: int = 0

    def as_dict(self) -> dict[str, int]:
        return {
            "discovered_files": self.discovered_files,
            "scanned_files": self.scanned_files,
            "scan_bytes": self.scan_bytes,
            "usage_lines_scanned": self.usage_lines_scanned,
            "usage_lines_prefiltered": self.usage_lines_prefiltered,
            "metadata_lines_scanned": self.metadata_lines_scanned,
            "metadata_lines_prefiltered": self.metadata_lines_prefiltered,
            "json_decode_attempts": self.json_decode_attempts,
            "discovery_ms": self.discovery_ms,
            "usage_parse_ms": self.usage_parse_ms,
            "metadata_parse_ms": self.metadata_parse_ms,
            "total_scan_ms": self.total_scan_ms,
            "duplicate_files_skipped": self.duplicate_files_skipped,
            "invalid_json_events": self.invalid_json_events,
            "non_object_json_events": self.non_object_json_events,
            "non_object_payload_events": self.non_object_payload_events,
            "malformed_usage_events": self.malformed_usage_events,
            "zero_usage_events": self.zero_usage_events,
            "cumulative_total_usage_events": self.cumulative_total_usage_events,
            "last_token_usage_events": self.last_token_usage_events,
            "headless_usage_events": self.headless_usage_events,
            "skipped_subagent_replay_events": self.skipped_subagent_replay_events,
            "usage_records": self.usage_records,
        }


@dataclass
class Aggregate:
    tokens: TokenUsage = field(default_factory=TokenUsage)
    cost: CostBreakdown = field(default_factory=CostBreakdown)
    events: int = 0
    sessions: set[str] = field(default_factory=set)
    files: set[str] = field(default_factory=set)

    def add(self, record: UsageRecord, cost: CostBreakdown) -> None:
        self.tokens.add(record.usage)
        self.cost.add(cost)
        self.events += 1
        self.sessions.add(record.session_id)
        self.files.add(record.path)

    def as_dict(self) -> dict[str, Any]:
        return {
            **self.tokens.as_dict(),
            **self.cost.as_dict(),
            "events": self.events,
            "sessions": len(self.sessions),
            "files": len(self.files),
        }
