from __future__ import annotations

import logging
import os
import re
from dataclasses import dataclass, field
from pathlib import Path

import yaml

logger = logging.getLogger("lazarus.config")


class ConfigError(Exception):
    pass


@dataclass
class Check:
    type: str
    timeout_seconds: float = 5.0
    port: int | None = None
    url: str | None = None
    name: str | None = None


@dataclass
class Remediation:
    on: str
    action: str
    service: str | None = None
    max_attempts: int = 1
    cooldown_seconds: float = 300.0


@dataclass
class Host:
    name: str
    address: str
    checks: list[Check]
    remediation: list[Remediation] = field(default_factory=list)
    ssh_user: str | None = None


@dataclass
class Alerting:
    webhook: str | None = None


@dataclass
class Config:
    hosts: list[Host]
    poll_interval_seconds: float = 60.0
    alerting: Alerting = field(default_factory=Alerting)
    debounce: int = 2


_ENV_PATTERN = re.compile(r"\$\{(\w+)\}")
_REQUIRED_FIELD = {"reachable": "port", "http_health": "url", "service": "name"}


def _expand_env(value: str) -> str:
    def replace(match: re.Match[str]) -> str:
        var = match.group(1)
        if var not in os.environ:
            raise ConfigError(f"environment variable {var} is not set")
        return os.environ[var]

    return _ENV_PATTERN.sub(replace, value)


def _float_field(raw: dict, key: str, default: float, *, minimum: float, inclusive: bool) -> float:
    try:
        value = float(raw.get(key, default))
    except (TypeError, ValueError):
        raise ConfigError(f"{key} must be a number, got {raw.get(key)!r}") from None
    if value < minimum or (value == minimum and not inclusive):
        bound = f">= {minimum}" if inclusive else f"> {minimum}"
        raise ConfigError(f"{key} must be {bound}, got {value}")
    return value


def _int_field(raw: dict, key: str, default: int, *, minimum: int) -> int:
    try:
        value = int(raw.get(key, default))
    except (TypeError, ValueError):
        raise ConfigError(f"{key} must be an integer, got {raw.get(key)!r}") from None
    if value < minimum:
        raise ConfigError(f"{key} must be >= {minimum}, got {value}")
    return value


def _parse_check(raw: dict) -> Check:
    ctype = raw.get("type")
    if ctype not in _REQUIRED_FIELD:
        raise ConfigError(f"unknown check type: {ctype!r}")
    required = _REQUIRED_FIELD[ctype]
    if raw.get(required) is None:
        raise ConfigError(f"{ctype} check requires a {required!r} field")
    return Check(
        type=ctype,
        timeout_seconds=_float_field(raw, "timeout_seconds", 5.0, minimum=0.0, inclusive=False),
        port=raw.get("port"),
        url=raw.get("url"),
        name=raw.get("name"),
    )


def _parse_remediation(raw: dict) -> Remediation:
    # YAML 1.1 parses a bare `on` key as boolean True, so accept either form.
    on = raw.get("on", raw.get(True))
    if on is None:
        raise ConfigError("remediation requires an 'on' field")
    if raw.get("action") is None:
        raise ConfigError("remediation requires an 'action' field")
    return Remediation(
        on=on,
        action=raw["action"],
        service=raw.get("service"),
        max_attempts=_int_field(raw, "max_attempts", 1, minimum=1),
        cooldown_seconds=_float_field(raw, "cooldown_seconds", 300.0, minimum=0.0, inclusive=True),
    )


def _parse_host(raw: dict) -> Host:
    for required in ("name", "address"):
        if raw.get(required) is None:
            raise ConfigError(f"host requires a {required!r} field")
    checks = [_parse_check(c) for c in raw.get("checks", [])]
    if not checks:
        raise ConfigError(f"host {raw['name']!r} has no checks")
    remediation = [_parse_remediation(r) for r in raw.get("remediation", [])]
    return Host(
        name=raw["name"],
        address=raw["address"],
        checks=checks,
        remediation=remediation,
        ssh_user=raw.get("ssh_user"),
    )


def load_config(path: str | Path) -> Config:
    try:
        raw = yaml.safe_load(Path(path).read_text()) or {}
    except yaml.YAMLError as exc:
        raise ConfigError(f"invalid YAML: {exc}") from exc
    if not isinstance(raw, dict):
        raise ConfigError("config root must be a mapping")
    if not raw.get("hosts"):
        raise ConfigError("config must define at least one host")
    hosts = [_parse_host(h) for h in raw["hosts"]]
    webhook = (raw.get("alerting") or {}).get("webhook")
    if isinstance(webhook, str):
        try:
            webhook = _expand_env(webhook)
        except ConfigError as exc:
            logger.warning("alerting disabled: %s", exc)
            webhook = None
    return Config(
        hosts=hosts,
        poll_interval_seconds=_float_field(
            raw, "poll_interval_seconds", 60.0, minimum=0.0, inclusive=False
        ),
        alerting=Alerting(webhook=webhook),
        debounce=_int_field(raw, "debounce", 2, minimum=1),
    )
