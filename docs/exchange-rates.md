# Exchange Rates And Fallback

The monitor uses Codex credits as the primary billing unit. Live exchange rates are optional and are only needed for secondary USD/ZAR diagnostics.

## Live Rate

Live USD/ZAR lookup is disabled by default:

```dotenv
FX_LIVE_ENABLED=false
```

In this mode, the dashboard may show the configured fallback rate with `live off`, but the monitor does not call any exchange-rate service.

To enable live lookup, set:

```dotenv
FX_LIVE_ENABLED=true
```

The live USD/ZAR rate is fetched from:

```text
https://open.er-api.com/v6/latest/USD
```

The fetched rate is cached per local day in SQLite.

This is intentionally separate from Valkey response caching. Exchange rates are source data for estimates, so they stay in durable SQLite state.

## Fallback Rate

If live fetching is disabled or fails, the monitor uses the configured fallback rate for legacy ZAR diagnostics:

```text
USD_ZAR_FALLBACK_RATE=18.50
```

When live FX is disabled, the dashboard shows this as:

```text
18.5 (live off)
```

When live FX is enabled but fetching fails, the dashboard shows this as:

```text
18.5 (fallback)
```

Fallback after enabling live FX can happen when:

- there is no network access from the container
- TLS verification fails
- the exchange-rate API is unavailable
- the API response does not contain `rates.ZAR`

## TLS Trust

Credits-only monitoring does not require a custom CA bundle. If `FX_LIVE_ENABLED=true`, fallback can happen if the container cannot verify a locally intercepted TLS certificate:

```text
SSL: CERTIFICATE_VERIFY_FAILED
self-signed certificate in certificate chain
```

If your environment needs this, export trusted certificates:

```sh
./scripts/export-macos-ca-bundle
```

Then set:

```dotenv
CUSTOM_CA_BUNDLE=/certs/macos-ca-bundle.pem
```

Do not disable SSL verification unless you are intentionally debugging a local network issue.

## Inspect Cached Rate

```sh
docker-compose -f docker-compose.yml exec -T monitor python - <<'PY'
import sqlite3
conn = sqlite3.connect('/data/monitor.sqlite3')
conn.row_factory = sqlite3.Row
for row in conn.execute('select * from fx_rates order by day desc limit 5'):
    print(dict(row))
PY
```

If a fallback rate was cached before TLS was fixed, it will remain until the next local day unless the cache is cleared while the service is stopped. Cached live and fallback rates are ignored while `FX_LIVE_ENABLED=false`.

Clear safely:

```sh
docker-compose -f docker-compose.yml stop monitor
docker-compose -f docker-compose.yml run --rm monitor python - <<'PY'
import sqlite3
conn = sqlite3.connect('/data/monitor.sqlite3')
conn.execute("delete from fx_rates where day = date('now')")
conn.commit()
PY
docker-compose -f docker-compose.yml up -d monitor
```
