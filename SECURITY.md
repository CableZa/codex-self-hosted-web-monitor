# Security Policy

## Supported Versions

Security fixes are applied to the current released version and the `main` branch.

## Reporting A Vulnerability

Please report security issues through GitHub Security Advisories for this repository. If advisories are not available to you, open a minimal public issue that says you have a security report to share, but do not include exploit details, secrets, tokens, or private logs in the issue.

Include:

- affected version or commit
- install method, Docker or local Windows
- steps to reproduce
- impact you believe is possible
- whether the issue needs network access, local host access, or access to `~/.codex`

## Trust Boundary

Codex Self-Hosted Web Monitor is designed as a local dashboard. The documented Docker deployment binds the host port to `127.0.0.1:18787`.

Do not expose the dashboard directly to a LAN or the public internet. If you need remote access, put it behind your own authentication, TLS, and network controls.

## What The App Reads

- Codex session JSONL files from `~/.codex/sessions` and `~/.codex/archived_sessions`.
- `~/.codex/auth.json` only to derive account identity metadata.
- Local app configuration from environment variables and `.env` values passed through Docker Compose.

In Docker, the host Codex directory is mounted read-only at `/codex`.

## What The App Stores

The app stores its own state in SQLite and derived cache entries in Valkey:

- settings
- alerts
- account limits
- daily aggregates
- exchange-rate cache rows
- auth snapshots containing safe identity metadata

Auth snapshots store account id, email, display name, source, and observation time. They do not store Codex access tokens, refresh tokens, or ID tokens from `auth.json`.

## What The App Sends

By default, the app does not send Codex session contents anywhere.

Outbound traffic is limited to:

- GitHub release tag checks when update checks are enabled.
- Optional USD/ZAR exchange-rate lookup when live FX is enabled.
- Optional JSON webhooks to the user-configured webhook URL.

Webhook payloads contain usage totals, budget or account-limit status, dashboard URL, and timestamps. They do not include raw session transcript content or auth tokens.

## Command Execution

The running API does not apply updates or run shell commands.

Local command execution is limited to explicit helper scripts such as `scripts/update-monitor.py apply`, which is run by the operator from the repo root. That script checks for a clean worktree, runs `git pull --ff-only`, redeploys Docker installs with Compose or restarts local Windows installs, then checks `/healthz`.

## Reproducible Checks

Install dev tooling and run:

```sh
python3 -m pip install -r requirements.txt -r requirements-dev.txt
npm ci
./scripts/security-audit
```

The audit command runs tests, dependency audits, static checks, Docker safety assertions, and targeted source searches for risky behavior.
