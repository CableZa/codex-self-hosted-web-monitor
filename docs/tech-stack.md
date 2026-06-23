# Tech Stack

This repo is a local Codex usage monitor with a Python API, a React dashboard, Docker Compose runtime services, and a small CLI report tool.

## Backend

- Python 3.13 in the production Docker image.
- FastAPI provides the HTTP API and static frontend hosting.
- Uvicorn runs the FastAPI app in the `monitor` container.
- Pydantic v2 defines API request and response schemas.
- httpx is used for outbound HTTP calls, including webhooks and optional service checks.
- redis-py connects to Valkey through the `redis://` protocol.
- Python's standard `sqlite3` module stores app-owned state in SQLite.

The service entry point is `monitor_service.py`, which creates the app from `codex_monitor.api`. Most monitor API behavior lives under `codex_monitor/`.

## Frontend

- React 18 powers the dashboard UI.
- TypeScript is used for application code and API-facing types.
- Vite 6 builds the frontend from `frontend/` into `static/`.
- Tailwind CSS provides the styling system.
- TanStack React Query handles API fetching, caching, and mutations in the browser.
- Recharts renders dashboard charts.
- Framer Motion provides small UI animations.
- Lucide React provides dashboard icons.

The production Docker image serves the built files from `static/` through FastAPI. For local frontend development, Vite proxies `/api` and `/healthz` to `http://127.0.0.1:18787`.

## Runtime Services

- Docker Compose is the normal runtime from the repo root.
- `monitor` builds the app image and serves the dashboard.
- `valkey` runs Valkey 8 for derived JSON response caching.

The dashboard is exposed on:

```text
http://127.0.0.1:18787
```

Docker maps host port `18787` to container port `8787`. Do not use host port `8787` directly for this app.

## Data And Storage

- Codex session data is read from `~/.codex/sessions` and `~/.codex/archived_sessions`.
- Docker mounts the host Codex home read-only at `/codex`.
- SQLite stores settings, alerts, summaries, auth snapshots, daily aggregates, and exchange-rate cache data.
- The app-owned SQLite schema is versioned in `sql/schema.sql`.
- Valkey stores derived dashboard cache entries. SQLite remains the source of truth for durable app state.
- Docker volumes hold runtime data: `monitor-data` and `valkey-data`.

## Tooling And Tests

- npm scripts run frontend development, type checking, linting, and builds:

```sh
npm run dev
npm run typecheck
npm run lint
npm run build
```

- ESLint 9, TypeScript ESLint, React Hooks lint rules, and React Refresh lint rules validate frontend code.
- `scripts/check-line-limits` enforces the hard 700-code-line limit for maintained files, excluding blank and comment-only lines and ignoring `package-lock.json`.
- The Dockerized test runner is `./scripts/test-docker`.
- Backend tests use Python `unittest`.
- `docker-compose.test.yml` defines backend and frontend check targets so tests can run without host Python or Node dependencies.

## Optional Integrations

- Webhooks can send budget, account limit, summary, and test payloads to user-configured endpoints.
- Live USD/ZAR exchange-rate lookup is optional. Credits mode is the default and does not require live FX.
