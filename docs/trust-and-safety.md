# Trust And Safety

This document explains how to verify the safety properties of Codex Self-Hosted Web Monitor. It is intended for public users and corporate reviewers who need more than a general statement of intent.

## Safety Claims

- The documented Docker deployment exposes the dashboard only on `127.0.0.1:18787`.
- The monitor reads Codex session files from a read-only Docker mount.
- The app stores derived usage data and settings in app-owned SQLite and Valkey state.
- The app does not store Codex access tokens, refresh tokens, or ID tokens.
- The API does not run update commands.
- Outbound traffic is limited and visible in source.

These are claims you can verify with the commands in this document.

## Data Flow

| Source | Use | Storage |
| --- | --- | --- |
| `~/.codex/sessions` | Parse token usage events and session metadata | Aggregated usage rows in SQLite and cache entries in Valkey |
| `~/.codex/archived_sessions` | Parse older token usage events | Aggregated usage rows in SQLite and cache entries in Valkey |
| `~/.codex/auth.json` | Derive current account id, email, and display name | Safe auth snapshots in SQLite |
| `.env` and Compose environment | Configure budgets, ports, cache, FX, update checks, and webhooks | Selected settings in SQLite |
| Dashboard browser | Reads API responses and stores UI preferences locally | Browser local storage only for local preferences |

The app should not receive raw secrets through the public API. Manual auth snapshots accept identity metadata, not token fields.

## Network Behavior

| Destination | Default | Why |
| --- | --- | --- |
| GitHub tags API | Enabled | Checks whether a newer stable release tag exists |
| `open.er-api.com` | Disabled | Optional live USD/ZAR lookup |
| User webhook URL | Disabled until configured | Sends budget, summary, account-limit, and test payloads |
| Valkey | Enabled inside Compose network | Derived JSON response cache |

Review source references:

- `codex_monitor/api_scanner_runtime.py` checks release tags.
- `codex_monitor/api_usage.py` performs optional FX lookup.
- `codex_monitor/api_alerts.py` sends optional webhooks.
- `codex_monitor/api_http.py` centralizes simple outbound URL helpers.

## Docker Isolation

The normal Docker deployment is intentionally local:

```yaml
ports:
  - "127.0.0.1:18787:8787"
```

The Codex directory is mounted read-only:

```yaml
- ${CODEX_HOST_HOME:-~/.codex}:/codex:ro
```

Runtime state is kept in named volumes:

- `monitor-data`
- `valkey-data`

Normal update and redeploy commands preserve those volumes.

## Command Execution

The web API exposes read and write endpoints for dashboard settings, account limits, manual auth snapshots, alerts, summaries, and webhook tests. It does not expose an update endpoint.

The command execution surface is the operator-run update helper:

```sh
python scripts/update-monitor.py apply
```

That script runs a narrow set of commands from the repo root:

- `git status --porcelain`
- `git pull --ff-only`
- Docker Compose redeploy for Docker installs
- PowerShell stop and start scripts for local Windows installs
- local health checks against `http://127.0.0.1:18787/healthz`

## Reproducible Audit

Install local tooling:

```sh
npm ci
python3 -m venv .venv
. .venv/bin/activate
python3 -m pip install -r requirements.txt -r requirements-dev.txt
```

Run the full audit:

```sh
./scripts/security-audit
```

The audit prints a Markdown report and fails if required checks fail. It covers:

- maintained-file line limits
- frontend lint
- frontend tests
- Python tests
- Python dependency audit
- npm production dependency audit
- Bandit static checks
- source searches for command execution and risky dynamic execution
- source searches for outbound network calls
- source searches for token handling
- Compose assertions for localhost binding and read-only Codex mount

## Release Evidence

GitHub Releases attach:

- release notes from the matching changelog section
- `security-audit.md`
- `sbom.cdx.json`

The release workflow runs the same audit command before publishing release assets.

## Known Limits

- The dashboard has no built-in login screen. Treat it as localhost-only unless you add external authentication and network controls.
- Optional webhooks send usage totals to the configured endpoint. Configure only endpoints you trust.
- Live FX lookup is optional and disabled by default.
- Update checks report available versions. Applying an update is an explicit operator action.
