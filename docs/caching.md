# Caching

The dashboard uses Valkey to avoid rescanning Codex session files for every page load.

## Services

Valkey runs inside Docker only:

```text
valkey:6379
```

It is not published on a host port. The monitor reaches it with:

```text
VALKEY_URL=redis://valkey:6379/0
```

Persistence is enabled with both AOF and RDB:

```sh
valkey-server --appendonly yes --save 60 1
```

The data volume is:

```text
valkey-data
```

## What Is Cached

Valkey stores derived JSON reports only:

- `/api/snapshot`
- `/api/days`
- `/api/summary`
- `/api/sessions`
- per-day usage rows used to build `/api/days` ranges

Zero-usage responses are not cached. If the monitor cannot find Codex session files, or if every usage total is zero, the next request scans again instead of serving a stale empty result. Usage with nonzero tokens can still be cached even when credits or USD are zero because missing model pricing can produce zero cost.

SQLite remains the source of truth for:

- settings
- alerts
- summaries
- exchange-rate cache

## TTL Policy

Today's data can change, so anything that includes today gets a short TTL:

```text
TODAY_CACHE_TTL_SECONDS=90
```

Historic-only ranges should not change in normal use, so they get a long TTL:

```text
HISTORIC_CACHE_TTL_SECONDS=604800
```

That is 7 days by default. This keeps older chart ranges fast while still allowing eventual refresh if archived session files are backfilled or prices change.

The dashboard's default 30-day chart includes today, so the exact range response uses the short TTL. The per-day rows inside that range are cached independently: today uses the short TTL, while yesterday and older days use the long TTL.

Datetime windows using `start_at` and `end_at` have separate cache keys from whole-day `date_from` and `date_to` ranges. This prevents a partial-day request from reusing a whole-day response.

## Day-Level Cache

The date-only chart endpoint has two cache layers:

- exact range cache, for example `days:v1:2026-05-01:2026-05-26`
- daily row cache, for example `day:v1:2026-05-01`

If the exact range is missing, `/api/days` tries to build the response from daily rows. If one or more daily rows are missing, the monitor scans the requested range once, stores each day separately, then returns the range response.

This means the first request for a cold date range can still take a few seconds if it has to scan Codex session files. After that, overlapping custom ranges should be fast because they can reuse the day rows already in Valkey. Empty day rows are not cached, so newly created or backfilled Codex files can appear without waiting for a long cache TTL.

Exact datetime windows scan the matching raw Codex records and cache the exact response. They do not compose from whole-day rows because the requested boundaries may split a day.

## Background Materialization

The separate scanner service refreshes common cache entries every minute before users request them:

- today
- yesterday
- current week
- current month
- previous month
- last 7 days
- last 30 days
- last 60 days
- last 90 days

Ranges that include today use the short TTL. Fully historic ranges use the long TTL.

This works like a small materialized view layer: page loads read the prepared JSON from Valkey instead of walking the Codex session tree.

The materializer also warms daily rows, so common custom ranges can be composed without rescanning.

## Logging

The monitor logs one line for each HTTP request:

```text
endpoint method=GET path=/api/days status=200 duration_ms=12.3
```

It also logs simple dependency spans:

```text
dependency name=cache.valkey.get duration_ms=0.4 key=day:v1:2026-05-01
dependency name=cache.memory.get duration_ms=0.1 key=day:v1:2026-05-01
dependency name=db.settings duration_ms=0.2
dependency name=service.codex_scan duration_ms=4210.7 start=2026-05-01 end=2026-05-26
dependency name=api.fx_rate duration_ms=320.0 day=2026-05-29
```

Use these lines to tell whether time is going into Valkey, SQLite, Codex file scanning, external APIs, or web calls.

Timing logs are enabled by default. Disable them with:

```text
DEBUG_TIMING_ENABLED=false
```

## Exchange Rates

Exchange rates are not stored in Valkey. They are cached in SQLite once per local day. That is effectively a 24-hour cache aligned with daily usage reports.

See `docs/exchange-rates.md`.

## Fallback Behavior

Cache access uses the async Redis client from the `redis` package, so Valkey I/O does not run on the API event loop.

If Valkey is unavailable, fallback depends on `CACHE_MEMORY_FALLBACK_MODE` and `MONITOR_API_WORKERS`:

- `single-worker` allows local in-memory fallback only when `MONITOR_API_WORKERS=1`.
- `disabled` turns cache reads into misses and cache writes into no-ops when Valkey is unavailable.
- `always` allows memory fallback with any worker count and should only be used for local development.

The application default is `single-worker` for single-process local installs. Docker Compose uses `disabled` because the API and scanner are separate processes and must communicate through Valkey, not per-process memory.

Derived response cache keys are also scoped by a shared SQLite-backed cache generation. Settings, auth snapshot, and account-limit changes bump that generation before clearing Valkey, so workers stop reading old cache namespaces immediately even if an older request finishes later.

If Valkey is unavailable during cache invalidation, the monitor marks the shared cache as dirty. It will not resume Valkey reads until it can clear the configured cache prefix, which prevents stale settings or account-derived report data from being served after reconnect.

The API response includes cache metadata so the dashboard or diagnostics can see whether data was cached.

## Clear Cache

This is a troubleshooting step, not a deployment step. It clears derived Valkey cache entries only and does not delete the SQLite database in the `monitor-data` volume.

Clear all Valkey cache data:

```sh
docker-compose -f docker-compose.yml exec -T valkey valkey-cli flushdb
```

Restart Valkey:

```sh
docker-compose -f docker-compose.yml restart valkey
```

Check Valkey:

```sh
docker-compose -f docker-compose.yml exec -T valkey valkey-cli ping
```
