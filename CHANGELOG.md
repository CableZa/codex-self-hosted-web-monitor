# Changelog

## Unreleased

### Changed

- Clarified the README positioning around Codex credit monitoring for Enterprise and credit-rated workspaces.

## v0.17.0 - 2026-06-23

### Added

- Added passive release checks from the scanner so Docker and local installs can detect newer stable tags without requiring a host scheduler.
- Added a dashboard update notice with the manual update command, copy action, and per-version dismissal.

### Fixed

- Adjusted the dashboard preview asset so header controls, chart toggles, and account cards fit at README thumbnail scale.

## v0.16.0 - 2026-06-23

### Initial Release

- Initial release of the Codex self-hosted web monitor.
- Includes the FastAPI monitor service, scanner runtime, SQLite persistence, Valkey-backed cache support, Docker Compose deployment, and local Windows start and stop scripts.
- Includes the React dashboard for usage overview, sessions, account limits, settings, alerts, update status, and changelog metadata.
- Includes setup, configuration, troubleshooting, update, sharing, and architecture documentation.

### Removed

- Removed local proxy support, UI controls, scripts, Compose service, and related documentation.

### Fixed

- Aligned the automatic account-limit reset default with the Friday reset used by the API schema.
- Updated the release workflow actions to avoid the GitHub Actions Node.js 20 deprecation warning.
- Replaced preview assets with fictionalized images that match the production dashboard appearance.
