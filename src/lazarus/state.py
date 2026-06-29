from __future__ import annotations

import json
import logging
import os
from dataclasses import asdict
from pathlib import Path

from lazarus.checks import CheckResult
from lazarus.detection import HostState, Incident

logger = logging.getLogger("lazarus.state")


def _host_dict(state: HostState, results: list[CheckResult]) -> dict:
    return {
        "name": state.name,
        "status": state.status,
        "confirmed_ok": state.confirmed_ok,
        "pending": state.pending,
        "checks": [asdict(r) for r in results],
        "open_incidents": [asdict(i) for i in state.incidents.values()],
    }


def write_state(
    path: str | Path,
    states: dict[str, HostState],
    results: dict[str, list[CheckResult]],
    timestamp: str,
) -> None:
    path = Path(path)
    payload = {
        "timestamp": timestamp,
        "hosts": [_host_dict(states[name], results.get(name, [])) for name in states],
    }
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(payload, indent=2))
    os.replace(tmp, path)


def load_state(path: str | Path) -> dict[str, HostState]:
    path = Path(path)
    if not path.exists():
        return {}
    try:
        data = json.loads(path.read_text())
        states: dict[str, HostState] = {}
        for host in data.get("hosts", []):
            state = HostState(
                name=host["name"],
                status=host.get("status", "healthy"),
                confirmed_ok=host.get("confirmed_ok", {}),
                pending=host.get("pending", {}),
            )
            for inc in host.get("open_incidents", []):
                state.incidents[inc["check_key"]] = Incident(**inc)
            states[host["name"]] = state
        return states
    except (OSError, ValueError, KeyError, TypeError) as exc:
        logger.warning("ignoring unreadable state file %s: %s", path, exc)
        return {}
