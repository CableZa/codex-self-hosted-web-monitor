# Repository Notes

- First-run setup guide for new users: `docs/setup.md`.
- Update `CHANGELOG.md` for every commit that will be pushed.
- Maintained files must stay at or below 700 lines of code, excluding blank and comment-only lines. Ignore `package-lock.json`. Run `scripts/check-line-limits` before committing.
- Use Semantic Versioning for release versions and tags, for example package/app version `0.2.0` with git tag `v0.2.0`.
- After any post-review edit, run another clean subagent review before committing or amending.
- Verify local git state after subagent activity before trusting a status report.
- For releases, confirm the package/app version, changelog section, commit, and tag all match.
- Pushing workflow files requires GitHub `workflow` scope.
- Run this app with Docker Compose from the repo root:
  `docker-compose up --build -d monitor scanner valkey`
- Windows users who cannot use Docker can run the local scripts from the repo root:
  `powershell -ExecutionPolicy Bypass -File .\scripts\start-local.ps1`
  and stop with:
  `powershell -ExecutionPolicy Bypass -File .\scripts\stop-local.ps1`
- For user updates, prefer `./scripts/update-and-redeploy`; for redeploying the current checkout, use `./scripts/redeploy`, then check `/healthz`.
- The scanner checks remote release tags on a schedule and writes `runtime/update-status.json`, which the dashboard exposes through `/api/update-status`. You can also run `python scripts/update-monitor.py check` manually.
- Use `python scripts/update-monitor.py apply` only from a clean worktree. It runs `git pull --ff-only`, then redeploys Docker installs with Docker Compose or restarts local Windows installs with the PowerShell scripts.
- Normal deploys must preserve runtime state. Prefer `docker-compose up --build -d ...` or `docker-compose restart ...`.
- Local Windows installs store runtime SQLite state in repo-root `monitor.sqlite3`; Docker installs store it in the `monitor-data` volume.
- Do not remove Docker volumes, delete SQLite databases, or run `docker-compose down -v` unless the user explicitly asks for a reset and a backup or recovery path has been considered.
- Optional startup overrides are documented in `.env.example`.
- The monitor dashboard must be served at `http://127.0.0.1:18787`.
- Do not use port `8787` directly on the host. In `docker-compose.yml`, host port `18787` maps to container port `8787`.
- Check the running service with:
  `curl http://127.0.0.1:18787/healthz`
- The `monitor` container serves the production frontend from `static/`; rebuild with Docker Compose after code or frontend changes.
