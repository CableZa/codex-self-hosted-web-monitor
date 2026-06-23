#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import platform
import re
import subprocess
import sys
import time
import urllib.error
import urllib.request
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[1]
STATUS_PATH = REPO_ROOT / "runtime" / "update-status.json"
HEALTH_URL = "http://127.0.0.1:18787/healthz"
SEMVER_TAG_RE = re.compile(r"^v(?P<version>\d+\.\d+\.\d+)$")
APP_VERSION_RE = re.compile(r'^APP_VERSION\s*=\s*"(?P<version>[^"]+)"\s*$')


@dataclass(frozen=True, order=True)
class SemVer:
    major: int
    minor: int
    patch: int

    @classmethod
    def parse(cls, value: str) -> "SemVer":
        match = re.match(r"^v?(\d+)\.(\d+)\.(\d+)$", value.strip())
        if not match:
            raise ValueError(f"invalid semver: {value}")
        return cls(*(int(part) for part in match.groups()))

    def __str__(self) -> str:
        return f"{self.major}.{self.minor}.{self.patch}"


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def run_command(args: list[str], check: bool = True) -> subprocess.CompletedProcess[str]:
    try:
        result = subprocess.run(
            args,
            cwd=REPO_ROOT,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            check=False,
        )
    except FileNotFoundError as exc:
        result = subprocess.CompletedProcess(args, 127, "", str(exc))
    if check and result.returncode != 0:
        detail = result.stderr.strip() or result.stdout.strip() or f"exit {result.returncode}"
        raise RuntimeError(f"{' '.join(args)} failed: {detail}")
    return result


def read_checkout_version() -> str:
    version_path = REPO_ROOT / "codex_monitor" / "version.py"
    for line in version_path.read_text(encoding="utf-8").splitlines():
        match = APP_VERSION_RE.match(line)
        if match:
            return match.group("version")
    raise RuntimeError("APP_VERSION not found")


def running_version(health_url: str = HEALTH_URL) -> str | None:
    try:
        with urllib.request.urlopen(health_url, timeout=3) as response:
            payload = json.loads(response.read().decode("utf-8"))
    except (OSError, urllib.error.URLError, json.JSONDecodeError):
        return None
    version = payload.get("version")
    return str(version) if version else None


def git_available() -> bool:
    return (REPO_ROOT / ".git").exists()


def latest_remote_tag(remote: str) -> tuple[str, str]:
    result = run_command(["git", "ls-remote", "--tags", "--refs", remote, "v*.*.*"])
    candidates: list[tuple[SemVer, str]] = []
    for line in result.stdout.splitlines():
        parts = line.split()
        if len(parts) != 2:
            continue
        tag = parts[1].removeprefix("refs/tags/")
        match = SEMVER_TAG_RE.match(tag)
        if not match:
            continue
        candidates.append((SemVer.parse(match.group("version")), tag))
    if not candidates:
        raise RuntimeError(f"no stable v*.*.* tags found on {remote}")
    latest_version, latest_tag = sorted(candidates)[-1]
    return str(latest_version), latest_tag


def dirty_worktree() -> str:
    return run_command(["git", "status", "--porcelain"], check=True).stdout.strip()


def compose_command() -> list[str] | None:
    if run_command(["docker-compose", "version"], check=False).returncode == 0:
        return ["docker-compose"]
    if run_command(["docker", "compose", "version"], check=False).returncode == 0:
        return ["docker", "compose"]
    return None


def local_pid_is_running() -> bool:
    pid_path = REPO_ROOT / ".monitor-local.pid"
    if not pid_path.exists():
        return False
    try:
        pid = int(pid_path.read_text(encoding="utf-8").strip())
    except ValueError:
        return False
    if platform.system().lower() == "windows":
        result = run_command(["powershell", "-NoProfile", "-Command", f"Get-Process -Id {pid}"], check=False)
        return result.returncode == 0
    result = run_command(["ps", "-p", str(pid)], check=False)
    return result.returncode == 0


def docker_monitor_is_running() -> bool:
    compose = compose_command()
    if compose is None:
        return False
    result = run_command([*compose, "ps", "-q", "monitor"], check=False)
    return bool(result.stdout.strip())


def detect_install_mode(requested: str) -> str:
    if requested != "auto":
        return requested
    if local_pid_is_running():
        return "local"
    if docker_monitor_is_running():
        return "docker"
    return "unknown"


def update_state(remote: str, health_url: str, install_mode: str) -> dict[str, Any]:
    checked_at = utc_now()
    checkout_version = read_checkout_version()
    active_version = running_version(health_url)
    if not git_available():
        return {
            "state": "unavailable",
            "checked_at": checked_at,
            "current_version": checkout_version,
            "running_version": active_version,
            "latest_version": None,
            "latest_tag": None,
            "install_mode": install_mode,
            "remote": remote,
            "message": "This checkout does not have git metadata, so remote updates cannot be checked.",
        }

    latest_version, latest_tag = latest_remote_tag(remote)
    compare_version = active_version or checkout_version
    state = "up_to_date"
    message = "Running version is current."
    if SemVer.parse(latest_version) > SemVer.parse(compare_version):
        state = "update_available"
        message = f"Version {latest_version} is available."
    elif active_version and SemVer.parse(checkout_version) > SemVer.parse(active_version):
        state = "update_available"
        latest_version = checkout_version
        latest_tag = None
        message = f"Checkout version {checkout_version} is newer than the running monitor."

    return {
        "state": state,
        "checked_at": checked_at,
        "current_version": checkout_version,
        "running_version": active_version,
        "latest_version": latest_version,
        "latest_tag": latest_tag,
        "install_mode": install_mode,
        "remote": remote,
        "message": message,
    }


def write_status(path: Path, status: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = {"generated_at": utc_now(), **status}
    tmp_path = path.with_suffix(f"{path.suffix}.tmp")
    tmp_path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    tmp_path.replace(path)


def check_updates(args: argparse.Namespace) -> dict[str, Any]:
    install_mode = detect_install_mode(args.install_mode)
    try:
        status = update_state(args.remote, args.health_url, install_mode)
    except Exception as exc:
        status = {
            "state": "checking_failed",
            "checked_at": utc_now(),
            "current_version": safe_checkout_version(),
            "running_version": running_version(args.health_url),
            "latest_version": None,
            "latest_tag": None,
            "install_mode": install_mode,
            "remote": args.remote,
            "message": "Update check failed.",
            "error": str(exc),
        }
    write_status(args.status_path, status)
    return status


def safe_checkout_version() -> str | None:
    try:
        return read_checkout_version()
    except Exception:
        return None


def wait_for_health(health_url: str, expected_version: str | None = None, timeout_seconds: int = 60) -> None:
    deadline = time.monotonic() + timeout_seconds
    last_version = None
    while time.monotonic() < deadline:
        last_version = running_version(health_url)
        if last_version and (expected_version is None or last_version == expected_version):
            return
        time.sleep(2)
    if expected_version:
        raise RuntimeError(f"health check did not report version {expected_version}; last version was {last_version}")
    raise RuntimeError("health check did not become available")


def deploy_docker(health_url: str) -> None:
    compose = compose_command()
    if compose is None:
        raise RuntimeError("docker-compose or docker compose is required for Docker updates")
    run_command([*compose, "up", "--build", "-d", "monitor", "scanner", "valkey"])
    wait_for_health(health_url)


def powershell_command() -> str:
    for name in ("pwsh", "powershell"):
        if run_command([name, "-NoProfile", "-Command", "$PSVersionTable.PSVersion"], check=False).returncode == 0:
            return name
    raise RuntimeError("PowerShell is required for local Windows updates")


def deploy_local(health_url: str) -> None:
    shell = powershell_command()
    stop_script = REPO_ROOT / "scripts" / "stop-local.ps1"
    start_script = REPO_ROOT / "scripts" / "start-local.ps1"
    run_command([shell, "-NoProfile", "-ExecutionPolicy", "Bypass", "-File", str(stop_script)])
    run_command([shell, "-NoProfile", "-ExecutionPolicy", "Bypass", "-File", str(start_script)])
    wait_for_health(health_url)


def apply_update(args: argparse.Namespace) -> dict[str, Any]:
    status = check_updates(args)
    if status["state"] != "update_available":
        return status
    if dirty_worktree() and not args.allow_dirty:
        status = {
            **status,
            "state": "update_failed",
            "message": "Update refused because the git worktree has uncommitted changes.",
        }
        write_status(args.status_path, status)
        return status

    install_mode = detect_install_mode(args.install_mode)
    if install_mode == "unknown":
        status = {
            **status,
            "state": "update_failed",
            "message": "Update refused because install mode could not be detected.",
        }
        write_status(args.status_path, status)
        return status

    write_status(args.status_path, {**status, "state": "updating", "message": "Updating monitor."})
    try:
        run_command(["git", "pull", "--ff-only"])
        if install_mode == "docker":
            deploy_docker(args.health_url)
        elif install_mode == "local":
            deploy_local(args.health_url)
        else:
            raise RuntimeError(f"unsupported install mode: {install_mode}")
        updated = update_state(args.remote, args.health_url, install_mode)
        updated["state"] = "up_to_date"
        updated["message"] = "Monitor updated successfully."
        write_status(args.status_path, updated)
        return updated
    except Exception as exc:
        failed = {
            **status,
            "state": "update_failed",
            "checked_at": utc_now(),
            "install_mode": install_mode,
            "message": "Update failed.",
            "error": str(exc),
        }
        write_status(args.status_path, failed)
        return failed


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Check and apply Codex Self-Hosted Web Monitor updates.")
    parser.add_argument("command", choices=("check", "apply"))
    parser.add_argument("--remote", default="origin")
    parser.add_argument("--health-url", default=HEALTH_URL)
    parser.add_argument("--status-path", type=Path, default=STATUS_PATH)
    parser.add_argument("--install-mode", choices=("auto", "docker", "local"), default="auto")
    parser.add_argument("--allow-dirty", action="store_true")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    result = apply_update(args) if args.command == "apply" else check_updates(args)
    print(json.dumps(result, indent=2, sort_keys=True))
    return 1 if result["state"] in {"checking_failed", "update_failed"} else 0


if __name__ == "__main__":
    raise SystemExit(main())
