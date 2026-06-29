from __future__ import annotations

import socket
import subprocess
import time
import urllib.error
import urllib.request
from collections.abc import Callable
from dataclasses import dataclass, field

from lazarus.config import Check, Host


@dataclass
class CheckResult:
    type: str
    ok: bool
    latency_ms: float | None = None
    detail: dict = field(default_factory=dict)
    error: str | None = None


def tcp_connect(address: str, port: int, timeout: float) -> None:
    with socket.create_connection((address, port), timeout=timeout):
        pass


def http_get_status(url: str, timeout: float) -> int:
    try:
        with urllib.request.urlopen(url, timeout=timeout) as resp:
            return resp.status
    except urllib.error.HTTPError as exc:
        return exc.code


def ssh_run(address: str, user: str | None, command: str, timeout: float) -> tuple[int, str]:
    target = f"{user}@{address}" if user else address
    proc = subprocess.run(
        ["ssh", "-o", "BatchMode=yes", target, command],
        capture_output=True,
        text=True,
        timeout=timeout,
    )
    return proc.returncode, (proc.stdout or proc.stderr).strip()


DEFAULT_RUNNERS: dict[str, Callable] = {
    "reachable": tcp_connect,
    "http_health": http_get_status,
    "service": ssh_run,
}


def _check_reachable(host: Host, check: Check, runner: Callable) -> CheckResult:
    start = time.monotonic()
    try:
        runner(host.address, check.port, check.timeout_seconds)
    except Exception as exc:
        return CheckResult(type=check.type, ok=False, error=str(exc))
    return CheckResult(
        type=check.type, ok=True, latency_ms=round((time.monotonic() - start) * 1000, 1)
    )


def _check_http(host: Host, check: Check, runner: Callable) -> CheckResult:
    start = time.monotonic()
    try:
        status = runner(check.url, check.timeout_seconds)
    except Exception as exc:
        return CheckResult(type=check.type, ok=False, error=str(exc))
    latency = round((time.monotonic() - start) * 1000, 1)
    return CheckResult(
        type=check.type, ok=200 <= status < 300, latency_ms=latency, detail={"status_code": status}
    )


def _check_service(host: Host, check: Check, runner: Callable) -> CheckResult:
    try:
        code, output = runner(
            host.address, host.ssh_user, f"systemctl is-active {check.name}", check.timeout_seconds
        )
    except Exception as exc:
        return CheckResult(type=check.type, ok=False, detail={"name": check.name}, error=str(exc))
    return CheckResult(type=check.type, ok=code == 0, detail={"name": check.name, "output": output})


_DISPATCH: dict[str, Callable[[Host, Check, Callable], CheckResult]] = {
    "reachable": _check_reachable,
    "http_health": _check_http,
    "service": _check_service,
}


def run_check(host: Host, check: Check, runners: dict[str, Callable] | None = None) -> CheckResult:
    runners = runners or DEFAULT_RUNNERS
    return _DISPATCH[check.type](host, check, runners[check.type])
