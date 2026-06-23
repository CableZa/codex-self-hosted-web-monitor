from __future__ import annotations

import csv
import html
import json
import sys
from pathlib import Path
from typing import Any, TextIO


def money(value: float) -> str:
    return f"${value:,.4f}"


def integer(value: int) -> str:
    return f"{value:,}"


def print_table(report: dict[str, Any], stream: TextIO = sys.stdout) -> None:
    period = report["period"]
    period_text = "all time"
    if period["from"] or period["to"]:
        period_text = f"{period['from'] or 'start'} to {period['to'] or 'today'}"

    totals = report["totals"]
    print("Codex usage estimate", file=stream)
    print(f"Period: {period_text}", file=stream)
    print(
        f"Files scanned: {report['files_scanned']}  "
        f"events: {report['usage_events']}  "
        f"sessions: {totals['sessions']}",
        file=stream,
    )
    print(f"Estimated cost: {money(totals['total_usd'])}", file=stream)
    print("", file=stream)

    print_rows(
        "By day",
        report["by_day"],
        ("day", "sessions", "events", "input_tokens", "cached_input_tokens", "output_tokens", "reasoning_output_tokens", "total_tokens", "total_usd"),
        stream,
    )
    print("", file=stream)
    print_rows(
        "By model",
        report["by_model"],
        ("model", "sessions", "events", "input_tokens", "cached_input_tokens", "output_tokens", "reasoning_output_tokens", "total_tokens", "total_usd"),
        stream,
    )
    print("", file=stream)
    print_rows(
        "By effort",
        report["by_effort"],
        ("effort", "sessions", "events", "input_tokens", "cached_input_tokens", "output_tokens", "reasoning_output_tokens", "total_tokens", "total_usd"),
        stream,
    )

    if report["warnings"]:
        print("", file=stream)
        print("Warnings", file=stream)
        for warning in report["warnings"]:
            print(f"- {warning}", file=stream)


def print_rows(title: str, rows: list[dict[str, Any]], columns: tuple[str, ...], stream: TextIO) -> None:
    print(title, file=stream)
    if not rows:
        print("  no usage found", file=stream)
        return

    labels = {
        "cached_input_tokens": "cached",
        "input_tokens": "input",
        "output_tokens": "output",
        "reasoning_output_tokens": "reasoning",
        "total_tokens": "total",
        "total_usd": "est usd",
    }
    table = []
    header = [labels.get(column, column) for column in columns]
    table.append(header)
    for row in rows:
        values = []
        for column in columns:
            value = row.get(column, "")
            if column.endswith("_tokens") or column in {"events", "sessions"}:
                values.append(integer(int(value)))
            elif column.endswith("_usd"):
                values.append(money(float(value)))
            else:
                values.append(str(value))
        table.append(values)

    widths = [max(len(row[index]) for row in table) for index in range(len(columns))]
    for index, row in enumerate(table):
        print("  " + "  ".join(cell.rjust(widths[pos]) for pos, cell in enumerate(row)), file=stream)
        if index == 0:
            print("  " + "  ".join("-" * width for width in widths), file=stream)


def write_json(report: dict[str, Any], stream: TextIO = sys.stdout) -> None:
    json.dump(report, stream, indent=2, sort_keys=True)
    stream.write("\n")


def write_csv(report: dict[str, Any], stream: TextIO = sys.stdout) -> None:
    fieldnames = [
        "group",
        "day",
        "model",
        "effort",
        "account",
        "sessions",
        "events",
        "input_tokens",
        "cached_input_tokens",
        "uncached_input_tokens",
        "output_tokens",
        "reasoning_output_tokens",
        "total_tokens",
        "total_usd",
        "long_context_applied",
    ]
    writer = csv.DictWriter(stream, fieldnames=fieldnames)
    writer.writeheader()

    rows = [{"group": "total", "day": "", "model": "", "effort": "", "account": "", **report["totals"]}]
    rows.extend({"group": "day", "model": "", "effort": "", "account": "", **row} for row in report["by_day"])
    rows.extend({"group": "model", "day": "", "effort": "", "account": "", **row} for row in report["by_model"])
    rows.extend({"group": "effort", "day": "", "model": "", "account": "", **row} for row in report["by_effort"])
    rows.extend({"group": "account", "day": "", "model": "", "effort": "", **row} for row in report["by_account"])
    rows.extend({"group": "day_model", "effort": "", "account": "", **row} for row in report["by_day_model"])
    rows.extend({"group": "day_account", "model": "", "effort": "", **row} for row in report["by_day_account"])
    rows.extend({"group": "model_effort", "day": "", "account": "", **row} for row in report["by_model_effort"])

    for row in rows:
        writer.writerow({field: row.get(field, "") for field in fieldnames})


def write_html(report: dict[str, Any], path: Path) -> None:
    data_json = json.dumps(report, indent=2)
    rows = "".join(
        "<tr>"
        f"<td>{html.escape(row['day'])}</td>"
        f"<td>{row['sessions']}</td>"
        f"<td>{row['events']}</td>"
        f"<td>{integer(row['input_tokens'])}</td>"
        f"<td>{integer(row['cached_input_tokens'])}</td>"
        f"<td>{integer(row['output_tokens'])}</td>"
        f"<td>{integer(row['reasoning_output_tokens'])}</td>"
        f"<td>{integer(row['total_tokens'])}</td>"
        f"<td>{money(row['total_usd'])}</td>"
        "</tr>"
        for row in report["by_day"]
    )
    model_rows = "".join(
        "<tr>"
        f"<td>{html.escape(row['model'])}</td>"
        f"<td>{row['sessions']}</td>"
        f"<td>{row['events']}</td>"
        f"<td>{integer(row['input_tokens'])}</td>"
        f"<td>{integer(row['cached_input_tokens'])}</td>"
        f"<td>{integer(row['output_tokens'])}</td>"
        f"<td>{integer(row['reasoning_output_tokens'])}</td>"
        f"<td>{integer(row['total_tokens'])}</td>"
        f"<td>{money(row['total_usd'])}</td>"
        "</tr>"
        for row in report["by_model"]
    )
    warnings = "".join(f"<li>{html.escape(warning)}</li>" for warning in report["warnings"])
    if not warnings:
        warnings = "<li>None</li>"

    document = f"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>Codex Usage Estimate</title>
  <style>
    :root {{
      color-scheme: light dark;
      --bg: #f7f7f4;
      --fg: #202124;
      --muted: #61645f;
      --line: #d8d8d0;
      --accent: #146c5f;
      --panel: #ffffff;
    }}
    @media (prefers-color-scheme: dark) {{
      :root {{
        --bg: #151614;
        --fg: #efefea;
        --muted: #b7b9b2;
        --line: #383a35;
        --accent: #5cc4b2;
        --panel: #20211f;
      }}
    }}
    body {{
      margin: 0;
      background: var(--bg);
      color: var(--fg);
      font: 14px/1.45 -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
    }}
    main {{
      max-width: 1180px;
      margin: 0 auto;
      padding: 32px 20px 48px;
    }}
    h1 {{
      margin: 0 0 6px;
      font-size: 28px;
      letter-spacing: 0;
    }}
    h2 {{
      margin: 28px 0 10px;
      font-size: 18px;
      letter-spacing: 0;
    }}
    .meta {{
      color: var(--muted);
      margin-bottom: 22px;
    }}
    .summary {{
      display: grid;
      grid-template-columns: repeat(auto-fit, minmax(190px, 1fr));
      gap: 12px;
    }}
    .metric {{
      background: var(--panel);
      border: 1px solid var(--line);
      border-radius: 8px;
      padding: 14px 16px;
    }}
    .metric span {{
      display: block;
      color: var(--muted);
      font-size: 12px;
      margin-bottom: 4px;
    }}
    .metric strong {{
      display: block;
      font-size: 22px;
      color: var(--accent);
    }}
    .table-wrap {{
      overflow-x: auto;
      border: 1px solid var(--line);
      background: var(--panel);
      border-radius: 8px;
    }}
    table {{
      width: 100%;
      border-collapse: collapse;
      min-width: 840px;
    }}
    th, td {{
      padding: 10px 12px;
      border-bottom: 1px solid var(--line);
      text-align: right;
      white-space: nowrap;
    }}
    th:first-child, td:first-child {{
      text-align: left;
    }}
    tr:last-child td {{
      border-bottom: 0;
    }}
    th {{
      color: var(--muted);
      font-weight: 600;
      font-size: 12px;
      text-transform: uppercase;
    }}
    pre {{
      white-space: pre-wrap;
      overflow-x: auto;
      background: var(--panel);
      border: 1px solid var(--line);
      border-radius: 8px;
      padding: 14px;
    }}
  </style>
</head>
<body>
  <main>
    <h1>Codex Usage Estimate</h1>
    <div class="meta">Generated {html.escape(report['generated_at'])}</div>
    <section class="summary">
      <div class="metric"><span>Estimated cost</span><strong>{money(report['totals']['total_usd'])}</strong></div>
      <div class="metric"><span>Total tokens</span><strong>{integer(report['totals']['total_tokens'])}</strong></div>
      <div class="metric"><span>Usage events</span><strong>{integer(report['usage_events'])}</strong></div>
      <div class="metric"><span>Sessions</span><strong>{integer(report['totals']['sessions'])}</strong></div>
    </section>
    <h2>By Day</h2>
    <div class="table-wrap">
      <table>
        <thead><tr><th>Day</th><th>Sessions</th><th>Events</th><th>Input</th><th>Cached</th><th>Output</th><th>Reasoning</th><th>Total</th><th>Est USD</th></tr></thead>
        <tbody>{rows or '<tr><td colspan="9">No usage found</td></tr>'}</tbody>
      </table>
    </div>
    <h2>By Model</h2>
    <div class="table-wrap">
      <table>
        <thead><tr><th>Model</th><th>Sessions</th><th>Events</th><th>Input</th><th>Cached</th><th>Output</th><th>Reasoning</th><th>Total</th><th>Est USD</th></tr></thead>
        <tbody>{model_rows or '<tr><td colspan="9">No usage found</td></tr>'}</tbody>
      </table>
    </div>
    <h2>Warnings</h2>
    <ul>{warnings}</ul>
    <h2>Raw Data</h2>
    <pre>{html.escape(data_json)}</pre>
  </main>
</body>
</html>
"""
    path.expanduser().write_text(document, encoding="utf-8")


def print_prices(prices: dict[str, Any], stream: TextIO = sys.stdout) -> None:
    rows = []
    for model, rates in sorted(prices["models"].items()):
        rows.append(
            {
                "model": model,
                "input": rates.get("input"),
                "cached_input": rates.get("cached_input", rates.get("input")),
                "output": rates.get("output"),
                "reasoning_output": rates.get("reasoning_output", rates.get("output")),
                "source": rates.get("source", ""),
            }
        )
    print("Prices are USD per 1M tokens.", file=stream)
    print_rows("Models", rows, ("model", "input", "cached_input", "output", "reasoning_output"), stream)
