from __future__ import annotations

import logging
import os
import time as monotonic_time
from contextlib import contextmanager
from typing import Any


def bool_env(name: str, default: bool) -> bool:
    value = os.environ.get(name)
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


LOG_LEVEL = os.environ.get("LOG_LEVEL", "INFO").upper()
DEBUG_TIMING_ENABLED = bool_env("DEBUG_TIMING_ENABLED", True)

logging.basicConfig(
    level=getattr(logging, LOG_LEVEL, logging.INFO),
    format="%(asctime)s %(levelname)s %(name)s %(message)s",
)
logger = logging.getLogger("codex_monitor")


@contextmanager
def timed_dependency(name: str, **fields: Any):
    if not DEBUG_TIMING_ENABLED:
        yield
        return

    started = monotonic_time.perf_counter()
    try:
        yield
    finally:
        duration_ms = (monotonic_time.perf_counter() - started) * 1000
        suffix = " ".join(f"{key}={value}" for key, value in fields.items())
        logger.info("dependency name=%s duration_ms=%.1f %s", name, duration_ms, suffix)
