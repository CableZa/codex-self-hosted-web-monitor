# Configuration

The monitor is configured with Docker Compose environment variables, SQLite-backed settings, and a few local files.

## Ports

- Dashboard: `http://127.0.0.1:18787`

The dashboard moved to `18787` because `8787` was already being served by another local app.

## Docker Compose Settings

Defined in `docker-compose.yml`.

| Setting | Default | Purpose |
| --- | --- | --- |
| `CODEX_HOST_HOME` | `~/.codex` | Host path mounted read-only into the monitor container. Use this for Windows or nonstandard Codex data paths. |
| `CODEX_HOME` | `/codex` | Read-only mount of local Codex data inside the monitor container. |
| `MONITOR_DB` | `/data/monitor.sqlite3` | SQLite database path inside the monitor container. |
| `TIMEZONE` | `UTC` | Local day, week, month, and summary schedule timezone. |
| `PRICING_MODE` | `credits` | Primary budget unit. Use `credits` for Codex credit budgets. |
| `FX_LIVE_ENABLED` | `false` | Enables live USD/ZAR lookup only when set to `true`. |
| `USD_ZAR_FALLBACK_RATE` | `18.50` | Manual exchange rate used for legacy ZAR diagnostics and live FX fallback. |
| `CUSTOM_CA_BUNDLE` | empty | Optional PEM path inside the container for outbound HTTPS trust. |
| `DAILY_BUDGET_CREDITS` | `100` | Daily credit budget override. |
| `WEEKLY_BUDGET_CREDITS` | `700` | Weekly credit budget override. |
| `MONTHLY_BUDGET_CREDITS` | `3000` | Monthly credit budget override. |
| `DASHBOARD_URL` | `http://127.0.0.1:18787` | URL included in webhook alerts and summaries. |
| `DASHBOARD_MODE` | `full` | Use `focused` to force dashboard data to focused work accounts. |
| `AUTO_ACCOUNT_LIMIT_EMAIL_SUFFIXES` | empty | Comma-separated email suffixes that receive automatic weekly account limits. Leave empty to disable automatic creation. |
| `AUTO_ACCOUNT_LIMIT_CAP_CREDITS` | `400` | Weekly credit cap used for automatic account limits. |
| `AUTO_ACCOUNT_LIMIT_RESET_WEEKDAY` | `4` | Reset weekday for automatic account limits, where Monday is `0` and Friday is `4`. |
| `AUTO_ACCOUNT_LIMIT_RESET_TIME` | `00:00` | Local reset time for automatic account limits. |
| `AUTO_ACCOUNT_LIMIT_TIMEZONE` | `UTC` | Timezone for automatic account limits. |
| `AUTO_ACCOUNT_LIMIT_THRESHOLDS` | `0.7,0.85,0.95,1.0` | Alert thresholds for automatic account limits. |
| `VALKEY_URL` | `redis://valkey:6379/0` | Valkey cache URL used by the monitor container. |
| `SCANNER_ENABLED` | `false` for Docker API, `true` for Docker scanner | Controls whether a process runs background scanning, summaries, snapshot publishing, and materialization. |
| `CACHE_MEMORY_FALLBACK_MODE` | `disabled` in Docker, `single-worker` in app defaults | Docker disables per-process memory fallback so the API and scanner share Valkey state. Keep this `disabled` for multi-worker Docker deploys. Use `always` only for local development. |
| `MONITOR_API_WORKERS` | `1` | Starts this many Uvicorn API workers in Docker through `scripts/run-api`. Raise it only when Valkey is healthy, memory fallback is disabled, and the scanner runs in its own process. |
| `TODAY_CACHE_TTL_SECONDS` | `90` | Cache TTL for ranges that include today. |
| `HISTORIC_CACHE_TTL_SECONDS` | `604800` | Cache TTL for historic-only ranges. |
| `DEFAULT_DAYS_BACK` | `30` | Default dashboard chart range before today. |
| `DEBUG_TIMING_ENABLED` | `true` | Enables endpoint and dependency timing logs. Set to `false` to disable them. |
| `FX_FALLBACK_RETRY_SECONDS` | `3600` | How long to reuse a fallback USD/ZAR rate before retrying the live FX API when live FX is enabled. |
| `UPDATE_STATUS_PATH` | `/runtime/update-status.json` in Docker | Host-written remote update status file shown by `/api/update-status`. |

## Dashboard Settings

The dashboard persists editable settings in SQLite:

- Daily budget credits, default `100`
- Weekly budget credits, default `700`
- Monthly budget credits, default `3000`
- Pricing mode, default `credits`
- Daily, weekly, and monthly ZAR budgets for legacy diagnostics
- Fallback USD/ZAR rate, default `18.50`, used for legacy ZAR diagnostics
- Webhook URL
- Dashboard mode, either `full` or `focused`. Focused mode filters to configured work account domains such as `@example.com` and `@example.org`.

Account credit caps also store their reset weekday and timezone. The dashboard exposes these as cap settings, and the backend calculates the current window and next reset time from them.

Credit budgets and account credit caps are stored as positive whole credit values.

Settings are exposed through:

```text
GET http://127.0.0.1:18787/api/settings
PUT http://127.0.0.1:18787/api/settings
```

## Codex Credit Rate Card

`prices.json` uses the OpenAI Help Center Codex token-based rate card as the primary source for Codex credits. As of June 3, 2026, the published token-based card applies to most Plus, Pro, Business, Enterprise, Edu, Health, Gov, and ChatGPT for Teachers customers.

A small subset of Enterprise customers may still use the legacy per-message rate card until migrated. Those workspaces should confirm their rate card with OpenAI sales before treating dashboard credit estimates as authoritative.

Fast mode also consumes more credits for supported models. The dashboard keeps this as a caveat because local Codex session logs do not always expose the selected service tier.

Long-context multipliers in `prices.json` are only used for secondary API-equivalent USD diagnostics. Codex credit totals use the published Codex rate card per 1M input, cached input, and output tokens.

## Persistent State

Docker volumes:

- `monitor-data`: SQLite database for settings, alerts, summaries, auth snapshots, account limits, and FX cache.
- `valkey-data`: Valkey cache persistence with AOF and RDB enabled.

Normal deployments must preserve these volumes. Use `docker-compose up --build -d ...` or `docker-compose restart ...` for updates. Do not remove volumes or run `docker-compose down -v` unless you are intentionally resetting the app and have considered whether the current state should be backed up.

Important files:

- `prices.json`: Codex credit rate card plus secondary USD per 1M token pricing estimates.
- `sql/schema.sql`: Versioned SQLite schema and indexes owned by this app.
- `.env`: local startup overrides, ignored by git.
- `certs/*.pem`: optional generated CA bundle files, ignored by git.
- `runtime/update-status.json`: generated by `scripts/update-monitor.py`, ignored by git.
- `monitor.sqlite3`: SQLite state for Windows local installs, ignored by git.

## CA Bundle

By default, credits-only monitoring does not need a custom certificate bundle. The containers use their normal image trust stores, and live USD/ZAR lookup is off unless `FX_LIVE_ENABLED=true`.

If your network requires a local CA bundle for live FX or HTTPS webhooks, generate `certs/macos-ca-bundle.pem` and set:

```dotenv
CUSTOM_CA_BUNDLE=/certs/macos-ca-bundle.pem
```

The generated PEM is ignored by git.

See `docs/setup.md#custom-ca-bundle` for the full macOS, Windows PowerShell, and WSL instructions.
