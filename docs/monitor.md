# Monitor Service

The monitor is a FastAPI service in `monitor_service.py`.

The dashboard UI is a Vite React app under `frontend/`. Its production build is written to `static/` and served by FastAPI.

## What It Reads

The monitor scans:

```text
~/.codex/sessions
~/.codex/archived_sessions
```

Inside Docker these are mounted read-only at:

```text
/codex/sessions
/codex/archived_sessions
```

It reuses the parser and pricing logic in `codex_usage.py`.

The app-owned SQLite schema lives in `sql/schema.sql`. It includes indexes for alert threshold lookups, recent alert listing, summary uniqueness, and FX day lookup.

The monitor also peeks at `~/.codex/auth.json` during the periodic scan. It stores only safe identity metadata in SQLite, not tokens:

- observed timestamp
- account id
- email
- display name
- source

Usage events are assigned to the most recent auth snapshot at or before the event timestamp. This lets the dashboard break down and filter usage by account after an account switch has been observed.

For already-existing history before the first observed snapshot, add a manual baseline snapshot with an old timestamp. For example, this marks all older usage as one account until a later snapshot is recorded:

```bash
curl -X POST http://127.0.0.1:18787/api/auth-snapshots \
  -H 'Content-Type: application/json' \
  -d '{"observed_at":"1970-01-01T00:00:00+00:00","email":"person@example.com","source":"manual"}'
```

## Scan Cadence

The service scans every minute.

It computes:

- today
- current week, Monday through today
- current month
- selected date-range totals
- selected date-range model and effort breakdowns
- selected date-range account breakdowns
- selected date-range session history with per-model breakdowns and a drilldown timeline

All periods use `UTC` by default.

The separate scanner service also prewarms Valkey cache entries for the dashboard snapshot, default chart range, and common ranges like yesterday, current week, current month, previous month, and last 7/30/60/90 days.

## Budgets

The dashboard uses Codex credits as the primary budget unit. Default credit budgets are:

- Daily: `100`
- Weekly: `700`
- Monthly: `3000`

Budget alerts are stored in SQLite. The monitor emits one alert when a period first crosses its limit, then repeat alerts at additional 25 percent overage increments.

## Account Credit Caps

Account caps are separate from the global credit budgets. They are intended for subscription-style limits where the service reports an account has hit a model or usage quota.

The dashboard always shows enabled account caps near the top of the page. A cap can be scoped to one account, so a work account can be monitored without affecting a personal account.

The primary cap metric is `total_credits`. Legacy `total_tokens` caps are auto-migrated by calculating the current account usage mix and applying its credits-per-token ratio to the old token cap. If no usage ratio can be calculated, the token cap is left in place and the service logs a warning.

The active window is reset-weekday based. For example, a Friday reset window runs from Friday through Thursday and resets at midnight on the next Friday in the configured timezone.

Account cap alerts use `account_limit_alert` webhook payloads. Each threshold is emitted once per account and reset window. The default thresholds are:

- 70 percent
- 85 percent
- 95 percent
- 100 percent

This is an alerting cap, not a traffic blocker. It does not stop Codex unless future traffic is routed through an enforcing proxy or wrapper.

## Summaries

The monitor sends same-day progress summaries at:

- `10:00`
- `15:00`

The summary schedule uses the configured timezone.

## Webhooks

Webhook alerts are generic JSON. Configure the webhook URL in the dashboard settings.

Payload types:

- `budget_alert`
- `account_limit_alert`
- `usage_summary`
- `test`

The webhook can target services such as Teams via Power Automate, Slack relays, Discord relays, ntfy, Gotify, Pushover, Zapier, Make, Home Assistant, or a custom endpoint.

## Endpoints

```text
GET  /healthz
GET  /api/snapshot
GET  /api/summary?period=today|week|month
GET  /api/summary?date_from=YYYY-MM-DD&date_to=YYYY-MM-DD
GET  /api/summary?date_from=YYYY-MM-DD&date_to=YYYY-MM-DD&accounts=email@example.com
GET  /api/summary?start_at=YYYY-MM-DDTHH:mm&end_at=YYYY-MM-DDTHH:mm
GET  /api/days?date_from=YYYY-MM-DD&date_to=YYYY-MM-DD
GET  /api/days?date_from=YYYY-MM-DD&date_to=YYYY-MM-DD&accounts=email@example.com
GET  /api/days?start_at=YYYY-MM-DDTHH:mm&end_at=YYYY-MM-DDTHH:mm
GET  /api/sessions?date_from=YYYY-MM-DD&date_to=YYYY-MM-DD
GET  /api/sessions?date_from=YYYY-MM-DD&date_to=YYYY-MM-DD&accounts=email@example.com
GET  /api/sessions?start_at=YYYY-MM-DDTHH:mm&end_at=YYYY-MM-DDTHH:mm
GET  /api/sessions/{session_id}?date_from=YYYY-MM-DD&date_to=YYYY-MM-DD
GET  /api/sessions/{session_id}?start_at=YYYY-MM-DDTHH:mm&end_at=YYYY-MM-DDTHH:mm
GET  /api/accounts
GET  /api/account-limits
PUT  /api/account-limits
GET  /api/events
GET  /api/settings
PUT  /api/settings
GET  /api/rate-card
GET  /api/alerts
POST /api/auth-snapshots
POST /api/test-webhook
```

`/api/events` is a server-sent events stream. The dashboard listens for `dashboard_update` events and refreshes visible data when the background scanner publishes a new snapshot.

The dashboard stores selected chart ranges in URL query parameters. Budget cards remain tied to current daily, weekly, and monthly periods.

The selected range view includes breakdown tables by account, model, and reasoning effort. Effort comes from Codex `turn_context` metadata when present, either `effort` or `collaboration_mode.settings.reasoning_effort`. Older or incomplete logs are grouped as `unknown`.

The Sessions tab shows one row per session with credits, uncached input tokens, cached input tokens, and output tokens. Each session row also shows which model or models were used, and expanding a row loads the raw usage timeline for that session.

Session context signals are conservative outlier flags:

- `high input volume`: at least 1,000,000 input tokens
- `high uncached input`: at least 250,000 uncached input tokens
- `low cache reuse`: at least 100,000 uncached input tokens and no more than 50 percent input cache reuse
- `large token footprint`: at least 1,500,000 total tokens
- `high output volume`: at least 100,000 output tokens
- `long-context pricing`: one or more events matched the local long-context pricing metadata

These signals are triage aids, not billing rules.

Thresholds can be changed from Settings. The defaults match the values above, and the settings also control whether long-context pricing appears as a visible session signal. These thresholds stay separate from budget alerts and account caps.

The chart supports line and bar modes. Short ranges default to bars because individual days are easier to compare; longer ranges default to lines for trend reading.

## Limitations

- Credits are estimates based on local token events and the configured Codex rate card.
- Unknown model names are priced as zero and reported in warnings.
- Fast mode can consume more credits, but current local session logs do not reliably expose selected service tier.
- ChatGPT subscription usage is not the same as API billing.
- This dashboard monitors and alerts on local usage. It does not enforce active cutoff.
