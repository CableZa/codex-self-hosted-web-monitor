from typing import Any

import codex_monitor.api as _api
from codex_monitor.api import create_app


app = create_app()


def __getattr__(name: str) -> Any:
    return getattr(_api, name)
