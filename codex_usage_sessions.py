from __future__ import annotations

import json
import re
import sys
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from time import perf_counter
from typing import Any, Iterable

from codex_usage_models import ParseDiagnostics, SessionMetadata, TokenUsage, UsageRecord


USAGE_LINE_MARKERS = (
    '"token_count"',
    '"last_token_usage"',
    '"total_token_usage"',
    '"usage"',
    '"session_meta"',
    '"turn_context"',
    '"model"',
    '"model_name"',
    '"effort"',
    '"collaboration_mode"',
)
METADATA_LINE_MARKERS = (
    '"session_meta"',
    '"turn_context"',
    '"user_message"',
    '"role"',
    '"tool"',
    '"status"',
    '"outcome"',
    '"is_error"',
    '"error"',
    '"cwd"',
    '"web_search"',
    '"web_fetch"',
    '"shell"',
    '"exec_command"',
)


def line_has_marker(line: str, markers: tuple[str, ...]) -> bool:
    return any(marker in line for marker in markers)


def parse_timestamp(value: Any) -> datetime:
    if isinstance(value, (int, float)):
        seconds = float(value) / 1000 if value > 10_000_000_000 else float(value)
        return datetime.fromtimestamp(seconds, timezone.utc)
    if not isinstance(value, str):
        raise ValueError("timestamp must be an ISO string or Unix timestamp")
    if value.endswith("Z"):
        value = value[:-1] + "+00:00"
    parsed = datetime.fromisoformat(value)
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed


def local_day(timestamp: datetime) -> str:
    return timestamp.astimezone().date().isoformat()


def discover_session_files(roots: Iterable[Path], diagnostics: ParseDiagnostics | None = None) -> list[Path]:
    started = perf_counter()
    files: list[Path] = []
    seen_resolved: set[Path] = set()
    seen_relative: set[tuple[str, Path]] = set()
    try:
        for root in roots:
            expanded = root.expanduser()
            if not expanded.exists():
                continue
            try:
                dedupe_scope = expanded.parent.resolve()
            except OSError:
                dedupe_scope = expanded.parent
            for path in sorted(expanded.rglob("*.jsonl")):
                resolved = path.resolve()
                try:
                    relative = path.relative_to(expanded)
                except ValueError:
                    relative = Path(path.name)
                relative_key = (str(dedupe_scope), relative)
                if resolved in seen_resolved or relative_key in seen_relative:
                    if diagnostics is not None:
                        diagnostics.duplicate_files_skipped += 1
                    continue
                seen_resolved.add(resolved)
                seen_relative.add(relative_key)
                files.append(path)
        if diagnostics is not None:
            diagnostics.discovered_files = len(files)
        return files
    finally:
        if diagnostics is not None:
            diagnostics.discovery_ms += round((perf_counter() - started) * 1000)


ROLLOUT_DATE_RE = re.compile(r"rollout-(\d{4})-(\d{2})-(\d{2})")


def session_file_day(path: Path) -> date | None:
    match = ROLLOUT_DATE_RE.search(path.name)
    if match:
        return date(int(match.group(1)), int(match.group(2)), int(match.group(3)))

    parts = path.parts
    for index in range(len(parts) - 2):
        year, month, day = parts[index : index + 3]
        if len(year) == 4 and len(month) == 2 and len(day) == 2:
            try:
                return date(int(year), int(month), int(day))
            except ValueError:
                continue
    return None


def filter_session_files_by_period(files: Iterable[Path], start_day: date | None, end_day: date | None) -> list[Path]:
    if start_day is None and end_day is None:
        return list(files)

    padded_start = start_day - timedelta(days=1) if start_day else None
    padded_end = end_day + timedelta(days=1) if end_day else None
    filtered: list[Path] = []
    for path in files:
        file_day = session_file_day(path)
        if file_day is None:
            filtered.append(path)
            continue
        if padded_start and file_day < padded_start:
            try:
                modified_day = datetime.fromtimestamp(path.stat().st_mtime).date()
            except OSError:
                continue
            if modified_day < padded_start:
                continue
        if padded_end and file_day > padded_end:
            continue
        filtered.append(path)
    return filtered


def default_session_roots(codex_home: Path) -> list[Path]:
    return [codex_home / "sessions", codex_home / "archived_sessions"]


def warn(message: str) -> None:
    print(f"warning: {message}", file=sys.stderr)


def nested_object(value: dict[str, Any], key: str) -> dict[str, Any] | None:
    nested = value.get(key)
    return nested if isinstance(nested, dict) else None


def first_nested_object(value: dict[str, Any], keys: Iterable[str]) -> dict[str, Any] | None:
    for key in keys:
        nested = nested_object(value, key)
        if nested is not None:
            return nested
    return None


def non_empty_string(value: Any) -> str | None:
    if isinstance(value, str) and value.strip():
        return value.strip()
    return None


def model_from_mapping(value: dict[str, Any]) -> str | None:
    metadata = nested_object(value, "metadata") or {}
    return (
        non_empty_string(value.get("model"))
        or non_empty_string(value.get("model_name"))
        or non_empty_string(metadata.get("model"))
    )


def timestamp_from_mapping(value: dict[str, Any]) -> Any:
    for key in ("timestamp", "created_at", "createdAt"):
        if key in value:
            return value.get(key)
    return None


def usage_from_mapping(value: dict[str, Any]) -> dict[str, Any] | None:
    usage = value.get("usage")
    if isinstance(usage, dict):
        return usage
    return None


def headless_usage_parts(event: dict[str, Any]) -> tuple[dict[str, Any], Any, str | None] | None:
    container = first_nested_object(event, ("data", "result", "response")) or event
    usage = usage_from_mapping(container)
    if usage is None and container is not event:
        usage = usage_from_mapping(event)
    if usage is None:
        return None
    timestamp_value = timestamp_from_mapping(container)
    if timestamp_value is None and container is not event:
        timestamp_value = timestamp_from_mapping(event)
    model = model_from_mapping(container) or (model_from_mapping(event) if container is not event else None)
    return usage, timestamp_value, model


def payload_effort(payload: dict[str, Any]) -> str | None:
    effort = payload.get("effort")
    if not isinstance(effort, str) or not effort:
        collaboration_mode = payload.get("collaboration_mode") or {}
        settings = collaboration_mode.get("settings") if isinstance(collaboration_mode, dict) else {}
        if isinstance(settings, dict):
            effort = settings.get("reasoning_effort")
    return effort if isinstance(effort, str) and effort else None


def token_count_info(event: dict[str, Any]) -> dict[str, Any] | None:
    payload = event.get("payload")
    if not isinstance(payload, dict) or payload.get("type") != "token_count":
        return None
    info = payload.get("info") or {}
    return info if isinstance(info, dict) else None


def timestamp_second(value: Any) -> str | None:
    try:
        return parse_timestamp(value).astimezone(timezone.utc).isoformat()[:19]
    except ValueError:
        return None


def detect_subagent_replay_second(path: Path) -> str | None:
    try:
        if "thread_spawn" not in path.read_text(encoding="utf-8", errors="ignore")[:32 * 1024]:
            return None
    except OSError:
        return None

    first_second: str | None = None
    try:
        with path.open("r", encoding="utf-8") as handle:
            for line in handle:
                if not line_has_marker(line, USAGE_LINE_MARKERS):
                    continue
                try:
                    event = json.loads(line)
                except json.JSONDecodeError:
                    continue
                if not isinstance(event, dict) or event.get("type") != "event_msg":
                    continue
                info = token_count_info(event)
                if not info or not (isinstance(info.get("last_token_usage"), dict) or isinstance(info.get("total_token_usage"), dict)):
                    continue
                second = timestamp_second(event.get("timestamp"))
                if second is None:
                    continue
                if first_second is None:
                    first_second = second
                    continue
                return first_second if second == first_second else None
    except OSError:
        return None
    return None


def parse_rollout(path: Path, diagnostics: ParseDiagnostics | None = None) -> Iterable[UsageRecord]:
    current_model = "unknown"
    current_effort = "unknown"
    session_id = path.stem
    previous_totals: TokenUsage | None = None
    replay_second = detect_subagent_replay_second(path)
    skip_replay = replay_second is not None

    with path.open("r", encoding="utf-8") as handle:
        for line_number, line in enumerate(handle, start=1):
            if diagnostics is not None:
                diagnostics.usage_lines_scanned += 1
            line = line.strip()
            if not line:
                continue
            if not line_has_marker(line, USAGE_LINE_MARKERS):
                if diagnostics is not None:
                    diagnostics.usage_lines_prefiltered += 1
                continue
            if diagnostics is not None:
                diagnostics.json_decode_attempts += 1
            try:
                event = json.loads(line)
            except json.JSONDecodeError:
                if diagnostics is not None:
                    diagnostics.invalid_json_events += 1
                warn(f"skipped invalid JSON in {path}:{line_number}")
                continue
            if not isinstance(event, dict):
                if diagnostics is not None:
                    diagnostics.non_object_json_events += 1
                warn(f"skipped non-object JSON in {path}:{line_number}")
                continue

            payload = event.get("payload") or {}
            if isinstance(payload, dict):
                if event.get("type") == "session_meta":
                    session_id = str(payload.get("id") or session_id)

                model = model_from_mapping(payload)
                if model:
                    current_model = model

                effort = payload_effort(payload)
                if effort:
                    current_effort = effort

            info = token_count_info(event)
            usage_data: dict[str, Any] | None = None
            timestamp_value = event.get("timestamp")
            model_for_record = current_model
            if info is not None:
                total_usage_data = info.get("total_token_usage")
                last_usage_data = info.get("last_token_usage")
                if isinstance(last_usage_data, dict):
                    usage_data = last_usage_data
                    if diagnostics is not None:
                        diagnostics.last_token_usage_events += 1
                elif isinstance(total_usage_data, dict):
                    try:
                        total_usage = TokenUsage.from_mapping(total_usage_data)
                    except ValueError as exc:
                        if diagnostics is not None:
                            diagnostics.malformed_usage_events += 1
                        warn(f"skipped malformed usage event in {path}:{line_number}: {exc}")
                        continue
                    usage = total_usage.subtract(previous_totals)
                    previous_totals = total_usage
                    if diagnostics is not None:
                        diagnostics.cumulative_total_usage_events += 1
                    if skip_replay and timestamp_second(timestamp_value) == replay_second:
                        if diagnostics is not None:
                            diagnostics.skipped_subagent_replay_events += 1
                        continue
                    skip_replay = False
                    if usage.is_zero():
                        if diagnostics is not None:
                            diagnostics.zero_usage_events += 1
                        continue
                    try:
                        timestamp = parse_timestamp(timestamp_value)
                    except ValueError as exc:
                        if diagnostics is not None:
                            diagnostics.malformed_usage_events += 1
                        warn(f"skipped malformed usage event in {path}:{line_number}: {exc}")
                        continue
                    if diagnostics is not None:
                        diagnostics.usage_records += 1
                    yield UsageRecord(
                        timestamp=timestamp,
                        day=local_day(timestamp),
                        model=model_from_mapping(info) or model_for_record,
                        effort=current_effort,
                        session_id=session_id,
                        path=str(path),
                        usage=usage,
                    )
                    continue
                if isinstance(total_usage_data, dict):
                    try:
                        previous_totals = TokenUsage.from_mapping(total_usage_data)
                    except ValueError:
                        pass
                if skip_replay and timestamp_second(timestamp_value) == replay_second:
                    if diagnostics is not None:
                        diagnostics.skipped_subagent_replay_events += 1
                    continue
                skip_replay = False
                model_for_record = model_from_mapping(info) or model_for_record
            else:
                headless = headless_usage_parts(event)
                if headless is None:
                    if "payload" in event and not isinstance(payload, dict):
                        if diagnostics is not None:
                            diagnostics.non_object_payload_events += 1
                        warn(f"skipped event with non-object payload in {path}:{line_number}")
                    continue
                usage_data, timestamp_value, headless_model = headless
                if diagnostics is not None:
                    diagnostics.headless_usage_events += 1
                if headless_model:
                    current_model = headless_model
                    model_for_record = headless_model

            try:
                timestamp = parse_timestamp(timestamp_value)
                usage = TokenUsage.from_mapping(usage_data)
            except ValueError as exc:
                if diagnostics is not None:
                    diagnostics.malformed_usage_events += 1
                warn(f"skipped malformed usage event in {path}:{line_number}: {exc}")
                continue
            if usage.is_zero():
                if diagnostics is not None:
                    diagnostics.zero_usage_events += 1
                continue
            if diagnostics is not None:
                diagnostics.usage_records += 1
            yield UsageRecord(
                timestamp=timestamp,
                day=local_day(timestamp),
                model=model_for_record,
                effort=current_effort,
                session_id=session_id,
                path=str(path),
                usage=usage,
            )


def compact_message_line(text: str, max_length: int = 180) -> str:
    lines = [line.strip() for line in text.replace("\r\n", "\n").replace("\r", "\n").split("\n")]
    text = " ".join(line for line in lines if line)
    text = re.sub(r"\s+", " ", text).strip()
    if len(text) <= max_length:
        return text
    return text[: max_length - 1].rstrip() + "..."


def content_text(value: Any) -> str:
    if isinstance(value, str):
        return value
    if isinstance(value, list):
        parts: list[str] = []
        for item in value:
            if isinstance(item, str):
                parts.append(item)
            elif isinstance(item, dict):
                text = item.get("text")
                if isinstance(text, str):
                    parts.append(text)
        return "\n".join(parts)
    return ""


def word_count(text: str) -> int:
    return len(re.findall(r"\b\w+\b", text))


def looks_large_ingest(text: str) -> bool:
    lowered = text.lower()
    return len(text) >= 20_000 or any(marker in lowered for marker in (".pdf", "attached", "paste", "document", "transcript", "dump"))


def tool_name_from_payload(payload: dict[str, Any]) -> str | None:
    payload_type = str(payload.get("type") or "").lower()
    candidates = (
        payload.get("tool_name"),
        payload.get("tool"),
        payload.get("name") if "tool" in payload_type or "call" in payload_type else None,
    )
    for candidate in candidates:
        if isinstance(candidate, str) and candidate.strip():
            return candidate.strip()
    if payload_type in {"web_search", "web_fetch", "shell", "exec_command"}:
        return payload_type
    return None


def tool_signature(payload: dict[str, Any], tool_name: str) -> str:
    compact = json.dumps(payload, sort_keys=True, default=str)[:500]
    return f"{tool_name}:{hash(compact)}"


def payload_is_tool_error(payload: dict[str, Any]) -> bool:
    status = str(payload.get("status") or payload.get("outcome") or "").lower()
    if status in {"error", "failed", "failure"}:
        return True
    if payload.get("is_error") is True or payload.get("error") is not None:
        return True
    text = json.dumps(payload, sort_keys=True, default=str).lower()[:1000]
    return "exit code" in text and "exit code 0" not in text


def is_web_tool(tool_name: str) -> bool:
    lowered = tool_name.lower()
    return any(part in lowered for part in ("web", "search", "fetch", "open"))


def is_synthetic_context_message(text: str) -> bool:
    lowered = text.lstrip().lower()
    return (
        lowered.startswith("# agents.md instructions")
        or lowered.startswith("<environment_context>")
        or lowered.startswith("<instructions>")
        or "<instructions>" in lowered[:500]
    )


def user_message_text(event: dict[str, Any], payload: dict[str, Any]) -> str | None:
    if event.get("type") == "event_msg" and payload.get("type") == "user_message":
        text = payload.get("message")
        if not isinstance(text, str) or not text.strip():
            text = content_text(payload.get("text_elements"))
        line = compact_message_line(text or "")
        if is_synthetic_context_message(line):
            return None
        return line or None

    return None


def fallback_user_message_text(event: dict[str, Any], payload: dict[str, Any]) -> str | None:
    if event.get("type") == "response_item" and payload.get("type") == "message" and payload.get("role") == "user":
        line = compact_message_line(content_text(payload.get("content")))
        if is_synthetic_context_message(line):
            return None
        return line or None

    return None


def project_name_from_path(path: str | None) -> str | None:
    if not path:
        return None
    name = Path(path).expanduser().name
    return name or path


def parse_rollout_metadata(path: Path, diagnostics: ParseDiagnostics | None = None) -> SessionMetadata:
    session_id = path.stem
    real_messages: list[str] = []
    fallback_messages: list[str] = []
    project_path: str | None = None
    user_message_count = 0
    first_message_word_count = 0
    tool_call_count = 0
    tool_error_count = 0
    consecutive_tool_errors = 0
    max_consecutive_tool_errors = 0
    web_tool_call_count = 0
    large_ingest_count = 0
    tool_signatures: dict[str, int] = {}

    with path.open("r", encoding="utf-8") as handle:
        for line_number, line in enumerate(handle, start=1):
            if diagnostics is not None:
                diagnostics.metadata_lines_scanned += 1
            line = line.strip()
            if not line:
                continue
            if not line_has_marker(line, METADATA_LINE_MARKERS):
                if diagnostics is not None:
                    diagnostics.metadata_lines_prefiltered += 1
                continue
            if diagnostics is not None:
                diagnostics.json_decode_attempts += 1
            try:
                event = json.loads(line)
            except json.JSONDecodeError:
                continue
            if not isinstance(event, dict):
                continue

            payload = event.get("payload") or {}
            if not isinstance(payload, dict):
                continue
            if event.get("type") == "session_meta":
                session_id = str(payload.get("id") or session_id)
                cwd = payload.get("cwd")
                if isinstance(cwd, str) and cwd and project_path is None:
                    project_path = cwd
            if event.get("type") == "turn_context":
                cwd = payload.get("cwd")
                if isinstance(cwd, str) and cwd and project_path is None:
                    project_path = cwd

            text = user_message_text(event, payload)
            if text and (not real_messages or text != real_messages[-1]):
                user_message_count += 1
                raw_text = payload.get("message") if isinstance(payload.get("message"), str) else content_text(payload.get("text_elements"))
                first_message_word_count = first_message_word_count or word_count(raw_text)
                if looks_large_ingest(raw_text):
                    large_ingest_count += 1
                real_messages.append(text)
                continue

            fallback_text = fallback_user_message_text(event, payload)
            if fallback_text and (not fallback_messages or fallback_text != fallback_messages[-1]):
                user_message_count += 1
                raw_text = content_text(payload.get("content"))
                first_message_word_count = first_message_word_count or word_count(raw_text)
                if looks_large_ingest(raw_text):
                    large_ingest_count += 1
                fallback_messages.append(fallback_text)

            tool_name = tool_name_from_payload(payload)
            if tool_name:
                tool_call_count += 1
                if is_web_tool(tool_name):
                    web_tool_call_count += 1
                signature = tool_signature(payload, tool_name)
                tool_signatures[signature] = tool_signatures.get(signature, 0) + 1
                if payload_is_tool_error(payload):
                    tool_error_count += 1
                    consecutive_tool_errors += 1
                    max_consecutive_tool_errors = max(max_consecutive_tool_errors, consecutive_tool_errors)
                else:
                    consecutive_tool_errors = 0

    messages = real_messages or fallback_messages
    first_message = messages[0] if messages else None
    last_message = messages[-1] if messages else None
    repeated_tool_signatures = sum(1 for count in tool_signatures.values() if count >= 3)
    return SessionMetadata(
        session_id=session_id,
        first_message=first_message,
        last_message=last_message,
        project_path=project_path,
        project_name=project_name_from_path(project_path),
        user_message_count=user_message_count,
        first_message_word_count=first_message_word_count,
        tool_call_count=tool_call_count,
        tool_error_count=tool_error_count,
        max_consecutive_tool_errors=max_consecutive_tool_errors,
        repeated_tool_signatures=repeated_tool_signatures,
        web_tool_call_count=web_tool_call_count,
        large_ingest_count=large_ingest_count,
    )


def read_session_metadata(files: Iterable[Path], diagnostics: ParseDiagnostics | None = None) -> dict[str, SessionMetadata]:
    started = perf_counter()
    metadata: dict[str, SessionMetadata] = {}
    try:
        for path in files:
            session_metadata = parse_rollout_metadata(path, diagnostics)
            existing = metadata.get(session_metadata.session_id)
            if existing is None:
                metadata[session_metadata.session_id] = session_metadata
                continue
            if existing.first_message is None:
                existing.first_message = session_metadata.first_message
            if session_metadata.last_message is not None:
                existing.last_message = session_metadata.last_message
            if existing.project_path is None:
                existing.project_path = session_metadata.project_path
                existing.project_name = session_metadata.project_name
            existing.user_message_count += session_metadata.user_message_count
            existing.first_message_word_count = existing.first_message_word_count or session_metadata.first_message_word_count
            existing.tool_call_count += session_metadata.tool_call_count
            existing.tool_error_count += session_metadata.tool_error_count
            existing.max_consecutive_tool_errors = max(existing.max_consecutive_tool_errors, session_metadata.max_consecutive_tool_errors)
            existing.repeated_tool_signatures += session_metadata.repeated_tool_signatures
            existing.web_tool_call_count += session_metadata.web_tool_call_count
            existing.large_ingest_count += session_metadata.large_ingest_count
        return metadata
    finally:
        if diagnostics is not None:
            diagnostics.metadata_parse_ms += round((perf_counter() - started) * 1000)


def read_records(
    files: Iterable[Path],
    start_day: date | None,
    end_day: date | None,
    start_at: datetime | None = None,
    end_at: datetime | None = None,
    diagnostics: ParseDiagnostics | None = None,
) -> list[UsageRecord]:
    started = perf_counter()
    records: list[UsageRecord] = []
    if not isinstance(files, list):
        files = list(files)
    if diagnostics is not None:
        diagnostics.scanned_files = len(files)
        for path in files:
            try:
                diagnostics.scan_bytes += path.stat().st_size
            except OSError:
                continue
    try:
        for path in files:
            for record in parse_rollout(path, diagnostics):
                if start_at and record.timestamp < start_at:
                    continue
                if end_at and record.timestamp >= end_at:
                    continue
                record_day = date.fromisoformat(record.day)
                if start_day and record_day < start_day:
                    continue
                if end_day and record_day > end_day:
                    continue
                records.append(record)
        return records
    finally:
        if diagnostics is not None:
            diagnostics.usage_parse_ms += round((perf_counter() - started) * 1000)
