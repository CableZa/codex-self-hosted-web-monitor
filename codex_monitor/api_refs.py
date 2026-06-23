from __future__ import annotations

import sys
from typing import Any


def api_module() -> Any:
    module = sys.modules.get("codex_monitor.api_app") or sys.modules.get("codex_monitor.api")
    if module is None:
        raise RuntimeError("codex monitor API module is not loaded")
    return module


class GlobalProxy:
    def __init__(self, name: str):
        object.__setattr__(self, "name", name)

    def target(self) -> Any:
        return getattr(api_module(), object.__getattribute__(self, "name"))

    def __getattr__(self, attr: str) -> Any:
        return getattr(self.target(), attr)

    def __getitem__(self, key: Any) -> Any:
        return self.target()[key]

    def __setitem__(self, key: Any, value: Any) -> None:
        self.target()[key] = value

    def get(self, *args: Any, **kwargs: Any) -> Any:
        return self.target().get(*args, **kwargs)

    def pop(self, *args: Any, **kwargs: Any) -> Any:
        return self.target().pop(*args, **kwargs)


store = GlobalProxy("store")
cache = GlobalProxy("cache")
inflight_usage_reports = GlobalProxy("inflight_usage_reports")
inflight_session_reports = GlobalProxy("inflight_session_reports")
inflight_diagnostics_reports = GlobalProxy("inflight_diagnostics_reports")


def active_http_client() -> Any:
    return api_module().active_http_client()
