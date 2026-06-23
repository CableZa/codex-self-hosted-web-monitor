from __future__ import annotations

import asyncio

from . import api_app
from .config import AppConfig
from .version import APP_VERSION


async def main_async() -> None:
    config = AppConfig.from_env()
    state = api_app.configure_runtime(config)
    settings = await state.store.settings()
    api_app.requested_snapshot_generation = await state.store.cache_generation()
    api_app.logger.info(
        "scanner_start version=%s pricing_mode=%s dashboard_mode=%s fx_live_enabled=%s",
        APP_VERSION,
        settings.get("pricing_mode") or config.pricing_mode,
        settings.get("dashboard_mode") or config.dashboard_mode,
        config.fx_live_enabled,
    )
    try:
        await api_app.scanner_loop()
    finally:
        await state.http_client.aclose()
        await state.cache.aclose()
        state.store.conn.close()


def main() -> None:
    try:
        asyncio.run(main_async())
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    main()
