# Update And Redeploy

## Public Repo Release Model

Use git tags as the source of truth for public releases:

```sh
git tag v0.16.0
git push origin v0.16.0
```

The updater looks for stable `v*.*.*` tags on the configured remote. It compares the latest tag with the version reported by `/healthz`, then writes the result to `runtime/update-status.json` for the dashboard.

Recommended defaults:

- publish normal releases from `main` with a semver tag
- keep user state outside git in Docker volumes or the local SQLite database
- require a clean worktree before applying updates
- use an external scheduler for automatic checks or automatic apply

## Docker Install

Use the helper script from the repo root:

```sh
./scripts/update-and-redeploy
```

It does three things:

- runs `git pull --ff-only`
- rebuilds and starts `monitor`, `scanner`, and `valkey` with Docker Compose
- checks `http://127.0.0.1:18787/healthz`

If you already pulled the latest code, redeploy the current checkout:

```sh
./scripts/redeploy
```

If you want to skip the pull step but use the same update script:

```sh
./scripts/update-and-redeploy --skip-pull
```

These scripts preserve Docker volumes. They do not remove SQLite databases or Valkey data.

Manual equivalent:

```sh
git pull --ff-only
docker-compose up --build -d monitor scanner valkey
curl http://127.0.0.1:18787/healthz
```

Do not use `docker-compose down -v` for normal updates.

## Windows Local Install

If the monitor was started with the local PowerShell scripts, update from the repo root with:

```powershell
git pull --ff-only
powershell -ExecutionPolicy Bypass -File .\scripts\stop-local.ps1
powershell -ExecutionPolicy Bypass -File .\scripts\start-local.ps1
Invoke-RestMethod http://127.0.0.1:18787/healthz
```

This keeps the repo-root `monitor.sqlite3` database. Do not delete it unless you intend to reset local dashboard state.

## Remote Update Check

Update detection uses the configured git remote and existing credentials:

```sh
python scripts/update-monitor.py check
```

To apply an available update from a clean worktree:

```sh
python scripts/update-monitor.py apply
```

For Docker installs, `apply` runs `git pull --ff-only`, rebuilds `monitor`, `scanner`, and `valkey`, then waits for `/healthz`.

For local PowerShell installs, `apply` runs `git pull --ff-only`, calls `scripts/stop-local.ps1`, calls `scripts/start-local.ps1`, then waits for `/healthz`.

The checker writes `runtime/update-status.json`. Docker reads that file through the read-only `/runtime` mount, and local Windows runs read it from the repo.

## Scheduling Updates

For unattended checks, schedule the check command:

```sh
python scripts/update-monitor.py check
```

For unattended apply, schedule:

```sh
python scripts/update-monitor.py apply --install-mode docker
```

or on Windows local installs:

```powershell
python .\scripts\update-monitor.py apply --install-mode local
```

Use unattended apply only when the checkout is dedicated to running the monitor. The updater refuses dirty worktrees unless `--allow-dirty` is passed.
