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
    # True when the check couldn't take a reading at all (SSH failed, output
    # unreadable). ok stays False so it never counts as a pass, but detection
    # ignores it: no reading is not proof the disk is full.
    unknown: bool = False


def tcp_connect(address: str, port: int, timeout: float) -> None:
    with socket.create_connection((address, port), timeout=timeout):
        pass


def http_get_status(url: str, timeout: float) -> int:
    try:
        with urllib.request.urlopen(url, timeout=timeout) as resp:
            return resp.status
    except urllib.error.HTTPError as exc:
        return exc.code


def ssh_run(
    address: str, user: str | None, command: str, timeout: float, port: int | None = None
) -> tuple[int, str]:
    target = f"{user}@{address}" if user else address
    proc = subprocess.run(
        ["ssh", "-o", "BatchMode=yes", *(["-p", str(port)] if port else []), target, command],
        capture_output=True,
        text=True,
        timeout=timeout,
    )
    return proc.returncode, (proc.stdout or proc.stderr).strip()


def ssh_options(host: Host) -> dict:
    """The keyword a runner gets only when the host sets one, so a runner without it still works."""
    return {"port": host.ssh_port} if host.ssh_port else {}


DEFAULT_RUNNERS: dict[str, Callable] = {
    "reachable": tcp_connect,
    "http_health": http_get_status,
    "service": ssh_run,
    "disk": ssh_run,
    "memory": ssh_run,
    "load": ssh_run,
    "swap": ssh_run,
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
        code, output = runner(
            host.address, host.ssh_user, command, check.timeout_seconds, **ssh_options(host)
        )
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
        code, output = runner(
            host.address, host.ssh_user, command, check.timeout_seconds, **ssh_options(host)
        )
    except Exception as exc:
        return CheckResult(type=check.type, ok=False, detail=detail, error=str(exc), unknown=True)
    used = _used_percent(output) if code == 0 else None
    if used is None:
        return CheckResult(
            type=check.type,
            ok=False,
            detail=detail,
            error=output or f"df exited {code}",
            unknown=True,
        )
    detail.update(used_percent=used, max_percent=check.max_percent)
    return CheckResult(type=check.type, ok=used <= check.max_percent, detail=detail)


def _used_memory_percent(meminfo: str) -> int | None:
    """Memory in use from /proc/meminfo: MemTotal less MemAvailable.

    Page cache the kernel could free is not counted as used.
    """
    fields = {}
    for line in meminfo.splitlines():
        name, _, rest = line.partition(":")
        parts = rest.split()
        if parts and parts[0].isdigit():
            fields[name.strip()] = int(parts[0])
    total, available = fields.get("MemTotal"), fields.get("MemAvailable")
    if not total or available is None:
        return None
    return round((total - available) * 100 / total)


def _check_memory(host: Host, check: Check, runner: Callable) -> CheckResult:
    try:
        code, output = runner(
            host.address,
            host.ssh_user,
            "cat /proc/meminfo",
            check.timeout_seconds,
            **ssh_options(host),
        )
    except Exception as exc:
        return CheckResult(type=check.type, ok=False, error=str(exc), unknown=True)
    used = _used_memory_percent(output) if code == 0 else None
    if used is None:
        return CheckResult(type=check.type, ok=False, error=output or f"exit {code}", unknown=True)
    detail = {"used_percent": used, "max_percent": check.max_percent}
    return CheckResult(type=check.type, ok=used <= check.max_percent, detail=detail)


def _load_percent(output: str) -> tuple[float, int, int] | None:
    """(5-minute load, cores, load as a percent of the cores) from `cat /proc/loadavg; nproc`."""
    lines = [ln.split() for ln in output.splitlines() if ln.strip()]
    try:
        load5, cores = float(lines[0][1]), int(lines[1][0])
    except (IndexError, ValueError):
        return None
    if cores < 1:
        return None
    return load5, cores, round(load5 * 100 / cores)


def _check_load(host: Host, check: Check, runner: Callable) -> CheckResult:
    try:
        code, output = runner(
            host.address,
            host.ssh_user,
            "cat /proc/loadavg; nproc",
            check.timeout_seconds,
            **ssh_options(host),
        )
    except Exception as exc:
        return CheckResult(type=check.type, ok=False, error=str(exc), unknown=True)
    got = _load_percent(output) if code == 0 else None
    if got is None:
        return CheckResult(type=check.type, ok=False, error=output or f"exit {code}", unknown=True)
    load5, cores, pct = got
    detail = {
        "load_5m": load5,
        "cores": cores,
        "used_percent": pct,
        "max_percent": check.max_percent,
    }
    return CheckResult(type=check.type, ok=pct <= check.max_percent, detail=detail)


def _swap(meminfo: str) -> tuple[int, int] | None:
    """(SwapTotal, SwapFree) in kB from /proc/meminfo; None when either is missing."""
    fields = {}
    for line in meminfo.splitlines():
        name, _, rest = line.partition(":")
        parts = rest.split()
        if parts and parts[0].isdigit():
            fields[name.strip()] = int(parts[0])
    total, free = fields.get("SwapTotal"), fields.get("SwapFree")
    return None if total is None or free is None else (total, free)


def _check_swap(host: Host, check: Check, runner: Callable) -> CheckResult:
    try:
        code, output = runner(
            host.address,
            host.ssh_user,
            "cat /proc/meminfo",
            check.timeout_seconds,
            **ssh_options(host),
        )
    except Exception as exc:
        return CheckResult(type=check.type, ok=False, error=str(exc), unknown=True)
    swap = _swap(output) if code == 0 else None
    if swap is None:
        return CheckResult(type=check.type, ok=False, error=output or f"exit {code}", unknown=True)
    total, free = swap
    if total == 0:
        # A box with no swap can't fill it; memory pressure there is the memory check's to see.
        return CheckResult(type=check.type, ok=True, detail={"swap": "none"})
    used = round((total - free) * 100 / total)
    detail = {"used_percent": used, "max_percent": check.max_percent}
    return CheckResult(type=check.type, ok=used <= check.max_percent, detail=detail)


_DISPATCH: dict[str, Callable[[Host, Check, Callable], CheckResult]] = {
    "reachable": _check_reachable,
    "http_health": _check_http,
    "service": _check_service,
    "disk": _check_disk,
    "memory": _check_memory,
    "load": _check_load,
    "swap": _check_swap,
}


def run_check(host: Host, check: Check, runners: dict[str, Callable] | None = None) -> CheckResult:
    runners = runners or DEFAULT_RUNNERS
    return _DISPATCH[check.type](host, check, runners[check.type])
