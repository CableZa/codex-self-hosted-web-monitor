from __future__ import annotations

import json
import urllib.parse
import urllib.request
from typing import Any


def validate_outbound_url(url: str, setting_name: str) -> str:
    parsed = urllib.parse.urlparse(url)
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        raise ValueError(f"{setting_name} must be an http or https URL")
    return url


def fetch_json_sync(url: str, timeout: float) -> dict[str, Any]:
    with urllib.request.urlopen(url, timeout=timeout) as response:
        return json.loads(response.read().decode("utf-8"))


def post_json_sync(url: str, payload: dict[str, Any], timeout: float) -> dict[str, Any]:
    body = json.dumps(payload).encode("utf-8")
    request = urllib.request.Request(url, data=body, headers={"Content-Type": "application/json"}, method="POST")
    with urllib.request.urlopen(request, timeout=timeout) as response:
        return {"sent": True, "status": response.status}


def probe_http_status_sync(url: str, timeout: float) -> int:
    with urllib.request.urlopen(url, timeout=timeout) as response:
        return int(response.status)
