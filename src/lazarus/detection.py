from __future__ import annotations

from dataclasses import dataclass, field

from lazarus.checks import CheckResult
from lazarus.config import Check

INCIDENT_TYPES = {
    "reachable": "host_unreachable",
    "http_health": "http_unhealthy",
    "service": "service_down",
}


@dataclass
class Incident:
    host: str
    type: str
    check_key: str
    target: str | None
    opened_at: float
    attempts: int = 0
    last_attempt: float | None = None


@dataclass
class Event:
    kind: str  # "opened" | "closed"
    incident: Incident


@dataclass
class HostState:
    name: str
    status: str = "healthy"
    confirmed_ok: dict[str, bool] = field(default_factory=dict)
    pending: dict[str, int] = field(default_factory=dict)
    incidents: dict[str, Incident] = field(default_factory=dict)


def check_key(check: Check) -> str:
    return f"{check.type}:{check.name or check.url or check.port or ''}"


def _target(check: Check) -> str | None:
    if check.type == "service":
        return check.name
    return check.url or (str(check.port) if check.port else None)


def evaluate(
    state: HostState,
    observations: list[tuple[Check, CheckResult]],
    debounce: int,
    now: float,
) -> list[Event]:
    events: list[Event] = []
    for check, result in observations:
        key = check_key(check)
        if result.ok == state.confirmed_ok.get(key, True):
            state.pending[key] = 0
            continue
        state.pending[key] = state.pending.get(key, 0) + 1
        if state.pending[key] < debounce:
            continue
        state.confirmed_ok[key] = result.ok
        state.pending[key] = 0
        if result.ok:
            incident = state.incidents.pop(key, None)
            if incident is not None:
                events.append(Event("closed", incident))
        else:
            incident = Incident(
                host=state.name,
                type=INCIDENT_TYPES[check.type],
                check_key=key,
                target=_target(check),
                opened_at=now,
            )
            state.incidents[key] = incident
            events.append(Event("opened", incident))
    state.status = _derive_status(state, observations)
    return events


def _derive_status(state: HostState, observations: list[tuple[Check, CheckResult]]) -> str:
    def failing(predicate) -> bool:
        return any(
            not state.confirmed_ok.get(check_key(c), True) for c, _ in observations if predicate(c)
        )

    if failing(lambda c: c.type == "reachable"):
        return "down"
    if failing(lambda c: c.type != "reachable"):
        return "degraded"
    return "healthy"
