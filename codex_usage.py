#!/usr/bin/env python3
"""Estimate Codex token usage cost from local session JSONL files."""

from __future__ import annotations

import argparse
import sys
from datetime import date, datetime, timedelta
from pathlib import Path

from codex_usage_constants import DEFAULT_CODEX_HOME, DEFAULT_PRICES_PATH, SCRIPT_DIR, TOKEN_FIELDS
from codex_usage_models import Aggregate, CostBreakdown, SessionMetadata, TokenUsage, UsageRecord
from codex_usage_output import integer, money, print_prices, print_rows, print_table, write_csv, write_html, write_json
from codex_usage_pricing import cost_for_usage, load_prices, lookup_rates
from codex_usage_reports import build_report, report_for_period
from codex_usage_sessions import (
    default_session_roots,
    discover_session_files,
    filter_session_files_by_period,
    local_day,
    parse_rollout,
    parse_rollout_metadata,
    parse_timestamp,
    read_records,
    read_session_metadata,
    session_file_day,
    warn,
)


def parse_day(value: str) -> date:
    try:
        return date.fromisoformat(value)
    except ValueError as exc:
        raise argparse.ArgumentTypeError("expected YYYY-MM-DD") from exc


def parse_days(value: str) -> int | None:
    if value == "all":
        return None
    try:
        days = int(value)
    except ValueError as exc:
        raise argparse.ArgumentTypeError("expected a positive integer or 'all'") from exc
    if days <= 0:
        raise argparse.ArgumentTypeError("days must be positive")
    return days


def resolve_period(args: argparse.Namespace) -> tuple[date | None, date | None]:
    if args.date_from or args.date_to:
        start_day = args.date_from
        end_day = args.date_to
    elif args.days is None:
        start_day = None
        end_day = None
    else:
        end_day = datetime.now().astimezone().date()
        start_day = end_day - timedelta(days=args.days - 1)

    if start_day and end_day and start_day > end_day:
        raise SystemExit("--from must be before or equal to --to")
    return start_day, end_day


def make_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Estimate local Codex token usage cost.")
    parser.add_argument("--prices", type=Path, default=DEFAULT_PRICES_PATH, help="Path to prices.json")
    subparsers = parser.add_subparsers(dest="command")

    summary = subparsers.add_parser("summary", help="Print a usage summary")
    summary.add_argument("--prices", type=Path, default=argparse.SUPPRESS, help="Path to prices.json")
    summary.add_argument("--days", type=parse_days, default=1, help="Days to include, or 'all' (default: 1)")
    summary.add_argument("--from", dest="date_from", type=parse_day, help="Start day, YYYY-MM-DD")
    summary.add_argument("--to", dest="date_to", type=parse_day, help="End day, YYYY-MM-DD")
    summary.add_argument("--format", choices=("table", "json", "csv"), default="table", help="Output format")
    summary.add_argument("--html", type=Path, help="Write a static HTML report")
    summary.add_argument("--codex-home", type=Path, default=DEFAULT_CODEX_HOME, help="Codex home directory")
    summary.add_argument(
        "--session-root",
        action="append",
        type=Path,
        help="Session root to scan. Repeatable. Defaults to ~/.codex/sessions and ~/.codex/archived_sessions.",
    )
    summary.set_defaults(func=run_summary)

    prices = subparsers.add_parser("prices", help="Show configured model prices")
    prices.add_argument("--prices", type=Path, default=argparse.SUPPRESS, help="Path to prices.json")
    prices.set_defaults(func=run_prices)
    return parser


def normalize_argv(argv: list[str] | None) -> list[str]:
    if argv is None:
        argv = sys.argv[1:]
    commands = {"summary", "prices"}
    if not argv or argv[0] not in commands and argv[0] not in {"-h", "--help"}:
        return ["summary", *argv]
    return argv


def run_summary(args: argparse.Namespace) -> int:
    roots = args.session_root or default_session_roots(args.codex_home.expanduser())
    start_day, end_day = resolve_period(args)
    report = report_for_period(start_day, end_day, args.prices, args.codex_home, roots)

    if args.format == "json":
        write_json(report)
    elif args.format == "csv":
        write_csv(report)
    else:
        print_table(report)

    if args.html:
        write_html(report, args.html)
        print(f"Wrote HTML report: {args.html.expanduser()}", file=sys.stderr)
    return 0


def run_prices(args: argparse.Namespace) -> int:
    prices = load_prices(args.prices)
    print_prices(prices)
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = make_parser()
    args = parser.parse_args(normalize_argv(argv))
    if not hasattr(args, "func"):
        parser.print_help()
        return 2
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
