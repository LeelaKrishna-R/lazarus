from __future__ import annotations

import shlex
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
    "disk": ssh_run,
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
        command = f"systemctl is-active {shlex.quote(check.name or '')}"
        code, output = runner(host.address, host.ssh_user, command, check.timeout_seconds)
    except Exception as exc:
        return CheckResult(type=check.type, ok=False, detail={"name": check.name}, error=str(exc))
    return CheckResult(type=check.type, ok=code == 0, detail={"name": check.name, "output": output})


def _used_percent(df_output: str) -> int | None:
    """The Capacity column of `df -P` for the one filesystem asked about."""
    lines = [ln for ln in df_output.splitlines() if ln.strip()]
    if len(lines) < 2:
        return None
    for part in lines[-1].split():
        if part.endswith("%") and part[:-1].isdigit():
            return int(part[:-1])
    return None


def _check_disk(host: Host, check: Check, runner: Callable) -> CheckResult:
    detail = {"path": check.path}
    try:
        command = f"df -P {shlex.quote(check.path or '')}"
        code, output = runner(host.address, host.ssh_user, command, check.timeout_seconds)
    except Exception as exc:
        return CheckResult(type=check.type, ok=False, detail=detail, error=str(exc))
    used = _used_percent(output) if code == 0 else None
    if used is None:
        return CheckResult(
            type=check.type, ok=False, detail=detail, error=output or f"df exited {code}"
        )
    detail.update(used_percent=used, max_percent=check.max_percent)
    return CheckResult(type=check.type, ok=used <= check.max_percent, detail=detail)


_DISPATCH: dict[str, Callable[[Host, Check, Callable], CheckResult]] = {
    "reachable": _check_reachable,
    "http_health": _check_http,
    "service": _check_service,
    "disk": _check_disk,
}


def run_check(host: Host, check: Check, runners: dict[str, Callable] | None = None) -> CheckResult:
    runners = runners or DEFAULT_RUNNERS
    return _DISPATCH[check.type](host, check, runners[check.type])
