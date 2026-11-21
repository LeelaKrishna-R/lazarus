"""The last poll as Prometheus text, for node_exporter's textfile collector.

Reads what `write_state` wrote; polls nothing. A state that can't be read is
still a valid exposition (``lazarus_state_readable 0``), so an alert can fire on
it instead of the series quietly going stale.
"""

from __future__ import annotations

from datetime import datetime


def _label(value: object) -> str:
    text = str(value)
    return text.replace("\\", "\\\\").replace('"', '\\"').replace("\n", "\\n")


def _epoch(timestamp: object) -> float | None:
    if not isinstance(timestamp, str):
        return None
    try:
        return datetime.fromisoformat(timestamp.replace("Z", "+00:00")).timestamp()
    except ValueError:
        return None


def _number(value: float) -> str:
    """Whole numbers as integers, anything else at full precision: never 1.795e+09 for a time."""
    return str(int(value)) if float(value).is_integer() else repr(float(value))


_HELP = {
    "lazarus_state_readable": "1 if the state file could be read.",
    "lazarus_last_poll_timestamp_seconds": "When the last poll wrote the state file.",
    "lazarus_host_healthy": "1 if the host's status was healthy at the last poll.",
    "lazarus_open_incidents": "Open incidents on the host, by type.",
    "lazarus_remediation_attempts": "Remediation attempts on the host's open incidents, by type.",
}


def render(data: dict | None) -> str:
    """Prometheus text exposition for a state dict, or for an unreadable one (None)."""
    lines: list[str] = []

    def metric(name: str, samples: list[tuple[str, float]]) -> None:
        lines.append(f"# HELP {name} {_HELP[name]}")
        lines.append(f"# TYPE {name} gauge")
        lines.extend(f"{name}{labels} {_number(value)}" for labels, value in samples)

    metric("lazarus_state_readable", [("", 0 if data is None else 1)])
    if data is None:
        return "\n".join(lines) + "\n"

    polled = _epoch(data.get("timestamp"))
    if polled is not None:
        metric("lazarus_last_poll_timestamp_seconds", [("", polled)])

    healthy, incidents, attempts = [], [], []
    for host in data.get("hosts", []):
        name = _label(host.get("name", ""))
        healthy.append((f'{{host="{name}"}}', 1 if host.get("status") == "healthy" else 0))
        counts: dict[str, list[float]] = {}
        for inc in host.get("open_incidents", []):
            n = counts.setdefault(str(inc.get("type", "")), [0, 0])
            n[0] += 1
            n[1] += inc.get("attempts") or 0
        for kind, (count, tries) in sorted(counts.items()):
            labels = f'{{host="{name}",type="{_label(kind)}"}}'
            incidents.append((labels, count))
            attempts.append((labels, tries))
    metric("lazarus_host_healthy", healthy)
    metric("lazarus_open_incidents", incidents)
    metric("lazarus_remediation_attempts", attempts)
    return "\n".join(lines) + "\n"
