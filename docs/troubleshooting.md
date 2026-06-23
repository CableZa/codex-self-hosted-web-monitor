# Troubleshooting

## Dashboard Does Not Open

Use:

```text
http://127.0.0.1:18787
```

Check services:

```sh
docker-compose -f docker-compose.yml ps
```

## Exchange Rate Shows Live Off

This is expected in the default setup. Credits mode does not need live USD/ZAR lookup.

Set this only if you need live exchange-rate diagnostics:

```dotenv
FX_LIVE_ENABLED=true
```

Then restart:

```sh
docker-compose up --build -d monitor scanner valkey
```

## Live Exchange Rate Shows Fallback

See `docs/exchange-rates.md`.

Most likely causes:

- no container network
- local TLS interception
- stale cached fallback value

If the fallback is caused by TLS interception, generate the CA bundle and set `CUSTOM_CA_BUNDLE`. The setup guide includes macOS and Windows PEM export commands.

```sh
./scripts/export-macos-ca-bundle
```

Then set:

```dotenv
CUSTOM_CA_BUNDLE=/certs/macos-ca-bundle.pem
```

See `docs/setup.md#custom-ca-bundle`.

## Dashboard Is Slow

Check Valkey:

```sh
docker-compose -f docker-compose.yml exec -T valkey valkey-cli ping
```

Check cache metadata:

```sh
curl http://127.0.0.1:18787/api/days
```

If Valkey is down, the monitor falls back to an in-memory cache and remains functional, but cold requests can rescan local Codex session files.

Clear cache only when troubleshooting cache behavior. This does not delete the SQLite database, but it is not part of a normal deployment:

```sh
docker-compose -f docker-compose.yml exec -T valkey valkey-cli flushdb
```

## SQLite Database Is Locked

The scanner may be reading usage while a manual SQLite command runs.

For manual maintenance, stop the monitor first:

```sh
docker-compose -f docker-compose.yml stop monitor
```

Then run the SQLite command, and start it again:

```sh
docker-compose -f docker-compose.yml up -d monitor
```

## Protect Persistent State

For normal deploys and restarts, use state-preserving commands:

```sh
docker-compose up --build -d monitor scanner valkey
docker-compose restart monitor
docker-compose down
```

Do not use `docker-compose down -v`, `docker volume rm`, or manual SQLite deletion unless you are intentionally resetting the app. Those actions can delete settings, auth snapshots, alerts, summaries, FX cache, and Valkey data.

The running Docker deployment stores its SQLite database at `/data/monitor.sqlite3` inside the `monitor-data` volume. A repo-root `monitor.sqlite3` is a local development database and may not match the running dashboard.

## Docker Socket Permission Errors

If a command returns:

```text
permission denied while trying to connect to the docker API
```

Retry the command. If it repeats, check Colima/Docker status:

```sh
docker ps
docker-compose -f docker-compose.yml ps
```

In this environment, some Docker socket operations required elevated approval.
