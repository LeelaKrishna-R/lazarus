from __future__ import annotations

import logging
from collections.abc import Callable
from dataclasses import dataclass

from lazarus.checks import ssh_run
from lazarus.config import Host, Remediation
from lazarus.detection import Incident

logger = logging.getLogger("lazarus.remediation")

SSH_TIMEOUT = 30.0


@dataclass
class RemediationResult:
    executed: bool
    command: str
    returncode: int | None = None
    output: str | None = None


def find_rule(host: Host, incident: Incident) -> Remediation | None:
    for rule in host.remediation:
        if rule.on != incident.type:
            continue
        if rule.service is not None and rule.service != incident.target:
            continue
        return rule
    return None


def should_remediate(incident: Incident, rule: Remediation, now: float) -> bool:
    if incident.attempts >= rule.max_attempts:
        return False
    if incident.last_attempt is not None and now - incident.last_attempt < rule.cooldown_seconds:
        return False
    return True


def remediate(
    host: Host,
    incident: Incident,
    rule: Remediation,
    now: float,
    dry_run: bool,
    runner: Callable | None = None,
) -> RemediationResult:
    if dry_run:
        logger.info("[dry-run] would run on %s: %s", host.name, rule.action)
        return RemediationResult(executed=False, command=rule.action)
    runner = runner or ssh_run
    logger.info("remediating %s on %s: %s", incident.type, host.name, rule.action)
    code, output = runner(host.address, host.ssh_user, rule.action, SSH_TIMEOUT)
    incident.attempts += 1
    incident.last_attempt = now
    return RemediationResult(executed=True, command=rule.action, returncode=code, output=output)
