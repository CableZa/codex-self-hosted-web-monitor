# Date Ranges

The dashboard supports preset and custom usage windows for the daily usage chart and Sessions tab.

## Controls

Presets:

- Today
- Last 48 hours
- Last 7
- Last 30
- Last 60
- Last 90
- Month to date
- Previous month

Custom range:

- Start date time
- End date time
- Reset

Custom changes apply automatically after a short delay when both values are valid. Datetimes are interpreted in the monitor's configured app timezone.

## URL Parameters

The selected range and chart options are stored in the URL:

```text
http://127.0.0.1:18787/?start_at=2026-05-01T08%3A30&end_at=2026-05-26T17%3A00&group=week&chart=bar
```

This means refreshes and shared links preserve:

- `start_at`
- `end_at`
- `group=day|week|month`
- `chart=bar|line`

Older links with `date_from=YYYY-MM-DD` and `date_to=YYYY-MM-DD` still work. The dashboard converts them to full-day windows.

## What Changes

The selected range updates:

- daily usage chart
- daily, weekly, or monthly chart grouping
- bar or line chart mode
- selected-range ZAR total
- selected-range total tokens
- selected-range input tokens
- selected-range output tokens
- selected-range cache status

The budget cards do not change. They always show current daily, weekly, and monthly budget periods.

## Caching

The dashboard calls:

```text
GET /api/days?start_at=YYYY-MM-DDTHH:mm&end_at=YYYY-MM-DDTHH:mm
```

Datetime windows use separate exact-window cache keys from whole-day date ranges. Windows that include today use the short cache TTL. Historic-only windows use the long cache TTL.

See `docs/caching.md`.
