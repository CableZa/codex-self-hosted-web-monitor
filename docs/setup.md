# Setup Guide

This guide is for a new user running Codex Self-Hosted Web Monitor for the first time.

The normal way to run the app is Docker Compose from the repo root. The dashboard is served at:

```text
http://127.0.0.1:18787
```

Do not open host port `8787` directly. Docker maps host port `18787` to container port `8787`.

This guide covers local Docker Compose setup for a single workstation. The app is intended to monitor local Codex usage from that machine's Codex home directory, not to run as a centralized multi-user service.

## Before You Start

Check these first:

- Docker is installed and running.
- Docker Compose is available.
- Codex has been used at least once on this machine.
- The Codex home directory exists.
- You are running commands from the repo root.

Quick checks:

```sh
docker --version
docker-compose version
```

If your Docker install uses the newer plugin command, this also works:

```sh
docker compose version
```

## Prerequisites

- Docker with Docker Compose support.
- Git, if you are cloning the repo.
- Codex already used at least once on this machine, so local session files exist under `~/.codex`.
- Optional: Node.js 22 or newer if you want to work on the frontend outside Docker.

The monitor reads these local Codex paths:

```text
~/.codex/sessions
~/.codex/archived_sessions
~/.codex/auth.json
```

Inside Docker, `~/.codex` is mounted read-only at `/codex`. The monitor stores only safe account metadata from `auth.json`, not tokens.

## Platform Commands

macOS or Linux:

```sh
git clone <repo-url>
cd codex-self-hosted-web-monitor
docker-compose up --build -d monitor scanner valkey
curl http://127.0.0.1:18787/healthz
```

Windows PowerShell with Docker Desktop:

```powershell
git clone <repo-url>
cd codex-self-hosted-web-monitor
Copy-Item .env.example .env
$codexHome = ($env:USERPROFILE -replace '\\','/') + '/.codex'
Add-Content .env "CODEX_HOST_HOME=$codexHome"
docker-compose up --build -d monitor scanner valkey
curl.exe http://127.0.0.1:18787/healthz
```

WSL using Linux Codex data:

```sh
git clone <repo-url>
cd codex-self-hosted-web-monitor
docker-compose up --build -d monitor scanner valkey
curl http://127.0.0.1:18787/healthz
```

WSL reading native Windows Codex data:

```sh
git clone <repo-url>
cd codex-self-hosted-web-monitor
cp .env.example .env
printf '\nCODEX_HOST_HOME=/mnt/c/Users/YourName/.codex\n' >> .env
docker-compose up --build -d monitor scanner valkey
curl http://127.0.0.1:18787/healthz
```

Replace `YourName` with your Windows user folder.

## Windows Codex Home

The native Windows Codex app uses:

```text
%USERPROFILE%\.codex
```

Docker Compose needs that directory mounted into the monitor container at `/codex`. If the default `~/.codex` mount does not resolve to the native Windows Codex directory, set `CODEX_HOST_HOME` in `.env`.

PowerShell or Command Prompt with Docker Desktop:

```dotenv
CODEX_HOST_HOME=C:/Users/YourName/.codex
```

You can also use the Windows environment variable form:

```dotenv
CODEX_HOST_HOME=${USERPROFILE}/.codex
```

If you run Docker Compose from WSL but want to read native Windows Codex data:

```dotenv
CODEX_HOST_HOME=/mnt/c/Users/YourName/.codex
```

On default WSL installs, the Windows `C:` drive is mounted under `/mnt/c`, so native Windows Codex data usually resolves to:

```text
/mnt/c/Users/YourName/.codex
```

Check the exact path from WSL:

```sh
wslpath "$(cmd.exe /c "echo %USERPROFILE%" 2>/dev/null | tr -d '\r')\\.codex"
```

If your WSL `/etc/wsl.conf` changes the automount root, use the path printed by `wslpath` instead of `/mnt/c/...`.

The container path stays `/codex`; only the host-side path changes.

### Windows Docker Permissions

You normally do not need to set a Linux UID or GID for this app on Windows. Docker Desktop handles access to the Windows profile folder when it bind-mounts `C:\Users\YourName\.codex` into the Linux container.

If the monitor cannot see `/codex/auth.json` or `/codex/sessions`, check these instead:

- `CODEX_HOST_HOME` points to the real Windows path, for example `C:/Users/YourName/.codex`.
- Docker Desktop is using the WSL 2 backend or has access to the drive that contains your user profile.
- The native Windows path exists before starting Compose: `%USERPROFILE%\.codex`.
- If running Compose from WSL, `CODEX_HOST_HOME` uses the WSL path, normally `/mnt/c/Users/YourName/.codex`.

The mount is read-only, so the monitor only needs read access to the host Codex files.

## Verify Codex Data

The dashboard is useful only after Codex has local session files. Empty directories are valid on a fresh install, but the monitor will show little or no usage until Codex writes session logs.

macOS or Linux:

```sh
test -d "$HOME/.codex" && echo "Codex home exists"
test -d "$HOME/.codex/sessions" && echo "sessions exists"
test -d "$HOME/.codex/archived_sessions" && echo "archived_sessions exists"
test -f "$HOME/.codex/auth.json" && echo "auth.json exists"
```

Windows PowerShell:

```powershell
Test-Path "$env:USERPROFILE\.codex"
Test-Path "$env:USERPROFILE\.codex\sessions"
Test-Path "$env:USERPROFILE\.codex\archived_sessions"
Test-Path "$env:USERPROFILE\.codex\auth.json"
```

WSL reading native Windows Codex data:

```sh
test -d "/mnt/c/Users/YourName/.codex" && echo "Codex home exists"
test -d "/mnt/c/Users/YourName/.codex/sessions" && echo "sessions exists"
test -d "/mnt/c/Users/YourName/.codex/archived_sessions" && echo "archived_sessions exists"
test -f "/mnt/c/Users/YourName/.codex/auth.json" && echo "auth.json exists"
```

If `sessions` or `archived_sessions` is missing, run Codex once and check again.

## First Startup

From the repo root:

```sh
docker-compose up --build -d monitor scanner valkey
```

Check the service:

```sh
curl http://127.0.0.1:18787/healthz
```

Open the dashboard:

```text
http://127.0.0.1:18787
```

The first scan may take a short time if you have many Codex sessions. The scanner runs every minute. If you have not used Codex before, the dashboard can start with no usage data.

## Windows Without Docker

Windows users who cannot install or run Docker can start the monitor directly with local PowerShell scripts.

From the repo root:

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\start-local.ps1
```

Stop it with:

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\stop-local.ps1
```

The script creates `.venv`, installs `requirements.txt`, reads `.env`, serves the committed `static/` frontend, and starts Uvicorn on:

```text
http://127.0.0.1:18787
```

Local Windows installs use repo-root `monitor.sqlite3` for dashboard state. Docker installs use the `monitor-data` volume instead.

If `static/index.html` is missing in a development checkout, install Node.js dependencies and build the frontend first:

```powershell
npm install
npm run build
```

## Optional Environment File

The app works without a `.env` file because `docker-compose.yml` provides safe defaults. To customize startup settings:

```sh
cp .env.example .env
```

Then edit `.env` and restart:

```sh
docker-compose up --build -d monitor scanner valkey
```

Useful first-run settings:

```dotenv
TIMEZONE=UTC
PRICING_MODE=credits
FX_LIVE_ENABLED=false
USD_ZAR_FALLBACK_RATE=18.50
DASHBOARD_URL=http://127.0.0.1:18787
WEBHOOK_URL=
AUTO_ACCOUNT_LIMIT_EMAIL_SUFFIXES=
AUTO_ACCOUNT_LIMIT_CAP_CREDITS=400
AUTO_ACCOUNT_LIMIT_RESET_WEEKDAY=4
AUTO_ACCOUNT_LIMIT_RESET_TIME=00:00
AUTO_ACCOUNT_LIMIT_TIMEZONE=UTC
DAILY_BUDGET_CREDITS=
WEEKLY_BUDGET_CREDITS=
MONTHLY_BUDGET_CREDITS=
```

Leave budget credit values blank to use the built-in defaults. Credits mode is the default and does not need live FX, ZAR conversion, or a custom CA bundle.

Leave `AUTO_ACCOUNT_LIMIT_EMAIL_SUFFIXES` empty for a generic install. To create default weekly credit limits automatically for known work accounts, set it to a comma-separated suffix list such as `@example.com,@team.example`. Matching accounts use the automatic cap, reset day, reset time, and timezone values above until you edit a limit in Settings.

## Required Runtime Config

The Docker Compose defaults are the recommended baseline:

| Setting | Default | Purpose |
| --- | --- | --- |
| `CODEX_HOME` | `/codex` | Container path for the read-only `~/.codex` mount. |
| `MONITOR_DB` | `/data/monitor.sqlite3` | SQLite database inside the `monitor-data` volume. |
| `TIMEZONE` | `UTC` | Local day, week, month, and summary timezone. |
| `PRICING_MODE` | `credits` | Uses Codex credits as the primary budget unit. |
| `FX_LIVE_ENABLED` | `false` | Enables live USD/ZAR lookup only when set to `true`. |
| `USD_ZAR_FALLBACK_RATE` | `18.50` | Fallback exchange rate used for legacy ZAR diagnostics. |
| `CUSTOM_CA_BUNDLE` | empty | Optional PEM path inside the container for outbound HTTPS trust. |
| `DASHBOARD_URL` | `http://127.0.0.1:18787` | URL included in alerts and summaries. |
| `AUTO_ACCOUNT_LIMIT_EMAIL_SUFFIXES` | empty | Comma-separated email suffixes that receive automatic weekly account limits. Leave empty to disable automatic creation. |
| `AUTO_ACCOUNT_LIMIT_CAP_CREDITS` | `400` | Weekly credit cap used for automatic account limits. |
| `AUTO_ACCOUNT_LIMIT_RESET_WEEKDAY` | `4` | Reset weekday for automatic account limits, where Monday is `0` and Friday is `4`. |
| `AUTO_ACCOUNT_LIMIT_RESET_TIME` | `00:00` | Local reset time for automatic account limits. |
| `AUTO_ACCOUNT_LIMIT_TIMEZONE` | `UTC` | Timezone for automatic account limits. |
| `AUTO_ACCOUNT_LIMIT_THRESHOLDS` | `0.7,0.85,0.95,1.0` | Alert thresholds for automatic account limits. |
| `VALKEY_URL` | `redis://valkey:6379/0` | Valkey cache URL inside Docker. |
| `SCANNER_ENABLED` | `false` for `monitor`, `true` for `scanner` | Controls whether a process runs background scanning and materialization. |
| `CACHE_MEMORY_FALLBACK_MODE` | `disabled` in Docker | Disables per-process memory fallback so API and scanner share Valkey state. Keep it disabled for multi-worker Docker runs. |
| `MONITOR_API_WORKERS` | `1` | Starts this many Uvicorn API workers in the `monitor` container. Raise it only after Valkey-backed cache checks pass. |
| `LOG_LEVEL` | `INFO` | Backend logging level. |
| `DEBUG_TIMING_ENABLED` | `true` | Enables timing logs for API calls and dependencies. |

For a nonstandard Codex data location, edit the `monitor` service volume in `docker-compose.yml`:

```yaml
volumes:
  - /path/to/your/codex/home:/codex:ro
```

Keep the container path `/codex` unless you also update `CODEX_HOME`.

The same host path can be set without editing Compose:

```dotenv
CODEX_HOST_HOME=/path/to/your/codex/home
```

## Privacy And Local Data

The monitor runs locally and reads local Codex files from the read-only `/codex` mount. It scans session JSONL files to estimate token usage and credits.

The monitor may read `/codex/auth.json` to identify which account was active when usage was recorded. It stores only safe identity metadata such as account id, email, display name, source, and observation time. It does not store access tokens, refresh tokens, or id tokens from `auth.json`.

Webhook alerts are optional. If `WEBHOOK_URL` is set, usage summaries and alerts are sent to that endpoint as JSON.

## Persistent Data

Docker volumes store runtime state:

- `monitor-data`: SQLite settings, alerts, summaries, auth snapshots, and FX cache.
- `valkey-data`: Valkey cache data.

Preserve these volumes during updates and normal deployments. They hold the dashboard history and identity snapshots used to attribute usage after account switches.

Local files used by the app:

- `prices.json`: Codex credit rate card and secondary token pricing estimates.
- `sql/schema.sql`: SQLite schema.
- `certs/macos-ca-bundle.pem`: optional generated CA bundle, ignored by git.

## Credit Rate Card

The dashboard estimates Codex credits from local token events and `prices.json`. The primary source is the OpenAI Help Center Codex token-based rate card.

Most Enterprise, Edu, Health, Gov, Business, Plus, and Pro customers use the token-based Codex rate card. A small subset of Enterprise customers can still be on the legacy per-message rate card. If that applies to your workspace, confirm the correct card with OpenAI sales before using these estimates for chargeback or budget decisions.

Fast mode can consume more credits for supported models. The monitor records this as a caveat because local Codex logs do not always expose whether a task used Fast mode.

Long-context multipliers in `prices.json` are only used for secondary API-equivalent USD diagnostics. Codex credit totals use the published Codex rate card per 1M input, cached input, and output tokens.

Credit calculation:

```text
uncached_input_tokens = input_tokens - min(cached_input_tokens, input_tokens)

credits =
  uncached_input_tokens / 1_000_000 * input_credit_rate
+ cached_input_tokens / 1_000_000 * cached_input_credit_rate
+ output_tokens / 1_000_000 * output_credit_rate
```

When Codex logs report reasoning output separately, the monitor only charges separate reasoning credits if `total_tokens` shows those tokens were not already included in `output_tokens`. In normal Codex token events, reasoning output is usually already included in output tokens.

See `prices.json` for the configured model rates and source link.

## Custom CA Bundle

Most users do not need a custom certificate bundle. Credits-only monitoring reads local Codex files and does not call the live FX API. Use this section only if you enable live FX, configure HTTPS webhooks, or see outbound TLS errors such as `CERTIFICATE_VERIFY_FAILED`, `self-signed certificate in certificate chain`, or if your company network uses TLS inspection.

The monitor container mounts:

```text
./certs:/certs:ro
```

Docker Compose does not point Python TLS clients at this file by default. After generating a PEM, opt in with:

```dotenv
CUSTOM_CA_BUNDLE=/certs/macos-ca-bundle.pem
```

The file name is `macos-ca-bundle.pem` for compatibility with the existing helper scripts. Windows users should write their exported PEM to the same path unless they choose a different `CUSTOM_CA_BUNDLE` value.

The PEM contains public CA certificates only. It should not contain Codex auth tokens, API keys, or private keys. The `certs/*.pem` files are ignored by git.

### macOS

Export the system and local machine keychains:

```sh
./scripts/export-macos-ca-bundle
grep -c 'BEGIN CERTIFICATE' certs/macos-ca-bundle.pem
```

Make sure `.env` contains `CUSTOM_CA_BUNDLE=/certs/macos-ca-bundle.pem` before restarting if you want the monitor to use this bundle:

```sh
docker-compose up --build -d monitor scanner valkey
```

This script reads:

```text
/System/Library/Keychains/SystemRootCertificates.keychain
/Library/Keychains/System.keychain
```

If your company root certificate is installed only in your login keychain and the export above is still missing it, export that certificate from Keychain Access:

1. Open Keychain Access.
2. Find the company root or intermediate certificate.
3. Export it as `.cer` or `.pem`.
4. Convert or append it to `certs/macos-ca-bundle.pem`.

For a PEM export, append it directly:

```sh
cat company-root.pem >> certs/macos-ca-bundle.pem
docker-compose up --build -d monitor scanner valkey
```

### Windows PowerShell

From the repo root in PowerShell, export Windows trusted root and intermediate certificates:

```powershell
.\scripts\export-windows-ca-bundle.ps1
(Select-String -Path .\certs\macos-ca-bundle.pem -Pattern "BEGIN CERTIFICATE").Count
```

Make sure `.env` contains `CUSTOM_CA_BUNDLE=/certs/macos-ca-bundle.pem` before restarting if you want the monitor to use this bundle:

```powershell
docker-compose up --build -d monitor scanner valkey
```

The script reads these public certificate stores:

```text
Cert:\CurrentUser\Root
Cert:\CurrentUser\CA
Cert:\LocalMachine\Root
Cert:\LocalMachine\CA
```

If PowerShell blocks the script for the current shell, run:

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\export-windows-ca-bundle.ps1
```

If your company gives you a root certificate file instead, place it under `certs` and make sure the final file is PEM encoded:

```powershell
New-Item -ItemType Directory -Force certs
Copy-Item .\company-root.pem .\certs\macos-ca-bundle.pem
docker-compose up --build -d monitor scanner valkey
```

### WSL

If you run Docker Compose from WSL and need the Windows certificate store, run the Windows PowerShell export from the Windows checkout of the repo, or call PowerShell from WSL:

```sh
powershell.exe -ExecutionPolicy Bypass -File "$(wslpath -w "$PWD/scripts/export-windows-ca-bundle.ps1")"
grep -c 'BEGIN CERTIFICATE' certs/macos-ca-bundle.pem
```

Make sure `.env` contains `CUSTOM_CA_BUNDLE=/certs/macos-ca-bundle.pem` before restarting if you want the monitor to use this bundle:

```sh
docker-compose up --build -d monitor scanner valkey
```

If the repo is checked out only inside WSL, the generated file still needs to exist at:

```text
./certs/macos-ca-bundle.pem
```

That path is mounted into the monitor container as `/certs/macos-ca-bundle.pem`.

## Frontend Development

The production dashboard is built into `static/` and served by the monitor container.

For local frontend development:

```sh
npm install
npm run dev
```

Before committing changes, prefer the Dockerized test runner so host Python and Node dependencies do not matter:

```sh
./scripts/test-docker
```

This runs backend `unittest` tests and frontend lint/build checks in Docker.

Equivalent manual commands:

```sh
COMPOSE_PROJECT_NAME=codex-web-monitor-test docker-compose -f docker-compose.test.yml build backend-test frontend-test
COMPOSE_PROJECT_NAME=codex-web-monitor-test docker-compose -f docker-compose.test.yml run --rm backend-test
COMPOSE_PROJECT_NAME=codex-web-monitor-test docker-compose -f docker-compose.test.yml down --remove-orphans
```

For fast local frontend-only checks:

```sh
npm run typecheck
npm run lint
npm run build
```

After frontend or backend code changes, rebuild the Docker service:

```sh
docker-compose up --build -d monitor scanner valkey
```

## Update The App

Normal updates should rebuild containers without removing volumes. The easiest path from the repo root is:

```sh
./scripts/update-and-redeploy
```

If you already pulled the latest code:

```sh
./scripts/redeploy
```

See `docs/update.md` for details.

For Windows local installs, use:

```powershell
git pull --ff-only
powershell -ExecutionPolicy Bypass -File .\scripts\stop-local.ps1
powershell -ExecutionPolicy Bypass -File .\scripts\start-local.ps1
```

For either install style, check remote release tags with:

```sh
python scripts/update-monitor.py check
```

Before updating, you can check the running services:

```sh
docker-compose ps
```

Confirm the monitor service uses the normal Docker database path:

```sh
docker-compose exec -T monitor python -c "import os; print(os.environ.get('MONITOR_DB'))"
```

The expected path is:

```text
/data/monitor.sqlite3
```

From the repo root:

```sh
git pull --ff-only
docker-compose up --build -d monitor scanner valkey
curl http://127.0.0.1:18787/healthz
curl http://127.0.0.1:18787/api/accounts
```

The rebuild updates the production frontend served from `static/` inside the monitor container. It preserves Docker volumes such as `monitor-data` and `valkey-data`.

Do not use these commands for normal updates:

```sh
docker-compose down -v
docker volume rm codex-self-hosted-web-monitor_monitor-data
docker volume rm codex-self-hosted-web-monitor_valkey-data
```

Those commands delete runtime state. Use them only for an intentional reset or uninstall.

## Useful Checks

Check containers:

```sh
docker-compose ps
```

View monitor logs:

```sh
docker-compose logs -f monitor
```

Check Valkey:

```sh
docker-compose exec -T valkey valkey-cli ping
```

Stop the stack:

```sh
docker-compose down
```

This keeps volumes and preserves settings, history, auth snapshots, cached FX rates, and Valkey cache data. Removing Docker volumes deletes persisted app state.

## Reset Or Uninstall

Before any destructive reset, confirm the reason, decide whether the state should be backed up, and verify you are not deleting the active deployment database by accident. The Docker deployment database is `/data/monitor.sqlite3` inside the `monitor-data` volume. A repo-root `monitor.sqlite3` is only a local development database.

Stop containers but keep persisted app data:

```sh
docker-compose down
```

Delete containers, networks, and all app-owned Docker volumes:

```sh
docker-compose down -v
```

Be careful with `docker-compose down -v`. It deletes:

- dashboard settings
- budgets and webhook settings
- alerts and summaries
- auth snapshots
- FX cache
- Valkey cache data

It does not delete your host `~/.codex` directory because that directory is mounted read-only from outside Docker.

## Troubleshooting

- Dashboard does not open: use `http://127.0.0.1:18787`, not host port `8787`.
- Health check fails: run `docker-compose ps` and `docker-compose logs monitor`.
- Usage is empty: confirm Codex has local files under `~/.codex/sessions` or `~/.codex/archived_sessions`.
- FX rate shows live off: this is expected in default credits mode. Set `FX_LIVE_ENABLED=true` only if you need live USD/ZAR diagnostics.
- FX rate uses fallback after live FX is enabled: generate the CA bundle or see `docs/exchange-rates.md`.

More details are in `docs/troubleshooting.md` and `docs/configuration.md`.
