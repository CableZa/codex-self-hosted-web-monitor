from __future__ import annotations

from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any, Callable

from codex_usage_constants import DEFAULT_CODEX_HOME, DEFAULT_PRICES_PATH
from codex_usage_models import Aggregate, CostBreakdown, UsageRecord
from codex_usage_pricing import cost_for_usage, load_prices, lookup_rates
from codex_usage_sessions import default_session_roots, discover_session_files, filter_session_files_by_period, read_records


def build_report(
    records: list[UsageRecord],
    prices: dict[str, Any],
    files_scanned: int,
    roots: list[Path],
    start_day: date | None,
    end_day: date | None,
    account_resolver: Callable[[UsageRecord], str] | None = None,
    account_filter: set[str] | None = None,
) -> dict[str, Any]:
    overall = Aggregate()
    by_day: dict[str, Aggregate] = {}
    by_model: dict[str, Aggregate] = {}
    by_effort: dict[str, Aggregate] = {}
    by_account: dict[str, Aggregate] = {}
    by_day_model: dict[tuple[str, str], Aggregate] = {}
    by_day_account: dict[tuple[str, str], Aggregate] = {}
    by_model_effort: dict[tuple[str, str], Aggregate] = {}
    warnings: set[str] = set()
    usage_events = 0

    for record in records:
        account = account_resolver(record) if account_resolver else record.account
        account = account or "unknown"
        if account_filter and account not in account_filter:
            continue
        priced_model, rates = lookup_rates(record.model, prices)
        model_key = priced_model or record.model
        if rates is None:
            warnings.add(f"No price found for model '{record.model}'. Cost for those events is $0.")
            cost = CostBreakdown()
        else:
            cost = cost_for_usage(record.usage, rates)
            if priced_model != record.model:
                warnings.add(f"Model '{record.model}' priced as '{priced_model}'.")

        overall.add(record, cost)
        usage_events += 1
        by_day.setdefault(record.day, Aggregate()).add(record, cost)
        by_model.setdefault(model_key, Aggregate()).add(record, cost)
        by_effort.setdefault(record.effort, Aggregate()).add(record, cost)
        by_account.setdefault(account, Aggregate()).add(record, cost)
        by_day_model.setdefault((record.day, model_key), Aggregate()).add(record, cost)
        by_day_account.setdefault((record.day, account), Aggregate()).add(record, cost)
        by_model_effort.setdefault((model_key, record.effort), Aggregate()).add(record, cost)

    def rows_from_day() -> list[dict[str, Any]]:
        return [
            {"day": day, **aggregate.as_dict()}
            for day, aggregate in sorted(by_day.items(), reverse=True)
        ]

    def rows_from_model() -> list[dict[str, Any]]:
        return [
            {"model": model, **aggregate.as_dict()}
            for model, aggregate in sorted(
                by_model.items(), key=lambda item: item[1].cost.total_credits, reverse=True
            )
        ]

    def rows_from_day_model() -> list[dict[str, Any]]:
        rows = []
        for (day, model), aggregate in sorted(by_day_model.items(), reverse=True):
            rows.append({"day": day, "model": model, **aggregate.as_dict()})
        return rows

    def rows_from_effort() -> list[dict[str, Any]]:
        return [
            {"effort": effort, **aggregate.as_dict()}
            for effort, aggregate in sorted(
                by_effort.items(), key=lambda item: item[1].cost.total_credits, reverse=True
            )
        ]

    def rows_from_account() -> list[dict[str, Any]]:
        return [
            {"account": account, **aggregate.as_dict()}
            for account, aggregate in sorted(
                by_account.items(), key=lambda item: item[1].cost.total_credits, reverse=True
            )
        ]

    def rows_from_day_account() -> list[dict[str, Any]]:
        rows = []
        for (day, account), aggregate in sorted(by_day_account.items(), reverse=True):
            rows.append({"day": day, "account": account, **aggregate.as_dict()})
        return rows

    def rows_from_model_effort() -> list[dict[str, Any]]:
        rows = []
        for (model, effort), aggregate in sorted(
            by_model_effort.items(), key=lambda item: item[1].cost.total_credits, reverse=True
        ):
            rows.append({"model": model, "effort": effort, **aggregate.as_dict()})
        return rows

    return {
        "generated_at": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        "period": {
            "from": start_day.isoformat() if start_day else None,
            "to": end_day.isoformat() if end_day else None,
        },
        "source_roots": [str(root.expanduser()) for root in roots],
        "files_scanned": files_scanned,
        "usage_events": usage_events,
        "totals": overall.as_dict(),
        "by_day": rows_from_day(),
        "by_model": rows_from_model(),
        "by_effort": rows_from_effort(),
        "by_account": rows_from_account(),
        "by_day_model": rows_from_day_model(),
        "by_day_account": rows_from_day_account(),
        "by_model_effort": rows_from_model_effort(),
        "warnings": sorted(warnings),
        "pricing_metadata": {
            "currency": prices.get("currency", "USD"),
            "unit": prices.get("unit", "per_1m_tokens"),
            "updated": prices.get("updated"),
            "credit_unit": prices.get("credit_unit", "per_1m_tokens"),
            "credit_source": prices.get("credit_source"),
            "notes": prices.get("notes", []),
        },
    }


def report_for_period(
    start_day: date | None,
    end_day: date | None,
    prices_path: Path = DEFAULT_PRICES_PATH,
    codex_home: Path = DEFAULT_CODEX_HOME,
    session_roots: list[Path] | None = None,
    account_resolver: Callable[[UsageRecord], str] | None = None,
    account_filter: set[str] | None = None,
) -> dict[str, Any]:
    prices = load_prices(prices_path)
    roots = session_roots or default_session_roots(codex_home.expanduser())
    files = filter_session_files_by_period(discover_session_files(roots), start_day, end_day)
    records = read_records(files, start_day, end_day)
    return build_report(
        records,
        prices,
        len(files),
        roots,
        start_day,
        end_day,
        account_resolver=account_resolver,
        account_filter=account_filter,
    )
