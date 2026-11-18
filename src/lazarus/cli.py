from __future__ import annotations

import argparse
import json
import logging
import sys
import time
from datetime import UTC, datetime
from pathlib import Path

from lazarus.alerter import format_alert, send_alert
from lazarus.checks import run_check
from lazarus.config import Config, ConfigError, load_config
from lazarus.detection import HostState, evaluate
from lazarus.remediation import find_rule, remediate, should_remediate
from lazarus.state import load_state, write_state

logger = logging.getLogger("lazarus")

STATE_PATH = Path("lazarus-state.json")


def _now_iso() -> str:
    return datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")


def run_cycle(
    config: Config,
    states: dict[str, HostState],
    dry_run: bool,
    state_path: Path = STATE_PATH,
    now_fn=time.time,
) -> int:
    any_incident = False
    results_by_host: dict[str, list] = {}
    for host in config.hosts:
        observations = [(check, run_check(host, check)) for check in host.checks]
        state = states.setdefault(host.name, HostState(name=host.name))
        for event in evaluate(state, observations, config.debounce, now_fn()):
            send_alert(config.alerting.webhook, format_alert(event))
            logger.info("%s %s on %s", event.kind, event.incident.type, host.name)
        for incident in state.incidents.values():
            rule = find_rule(host, incident)
            if rule and should_remediate(incident, rule, now_fn()):
                remediate(host, incident, rule, now_fn(), dry_run)
        results_by_host[host.name] = [r for _, r in observations]
        logger.info("host %s: %s", host.name, state.status)
        any_incident = any_incident or bool(state.incidents)
    write_state(state_path, states, results_by_host, _now_iso())
    return 1 if any_incident else 0


def _when(epoch: float) -> str:
    return datetime.fromtimestamp(epoch, UTC).strftime("%Y-%m-%d %H:%M:%SZ")


def show_status(state_path: Path, out=sys.stdout) -> int:
    """The last poll as the state file has it, without polling anything.

    Prints each host's status and its open incidents. Returns 0 when nothing is
    open, 1 when something is, 2 when there's no readable state yet.
    """
    try:
        data = json.loads(state_path.read_text())
        hosts = data["hosts"]
    except FileNotFoundError:
        print(f"no state at {state_path} yet; run `lazarus run-once` first", file=out)
        return 2
    except (OSError, ValueError, KeyError, TypeError) as exc:
        print(f"can't read {state_path}: {exc}", file=out)
        return 2
    print(f"last poll: {data.get('timestamp') or 'unknown'}", file=out)
    open_any = False
    for host in hosts:
        print(f"{host.get('name')}: {host.get('status', 'unknown')}", file=out)
        for inc in host.get("open_incidents", []):
            open_any = True
            target = f" ({inc['target']})" if inc.get("target") else ""
            reason = f": {inc['reason']}" if inc.get("reason") else ""
            tries = f", {inc['attempts']} remediation attempt(s)" if inc.get("attempts") else ""
            since = _when(inc["opened_at"])
            print(f"  open {inc.get('type')}{target}{reason} since {since}{tries}", file=out)
    return 1 if open_any else 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="lazarus")
    parser.add_argument("command", choices=["run-once", "daemon", "status"])
    parser.add_argument("--config")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--state", default=str(STATE_PATH))
    args = parser.parse_args(argv)

    if args.command == "status":  # reads the state file only; needs no config
        return show_status(Path(args.state))
    if not args.config:
        parser.error("--config is required for run-once and daemon")

    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")

    try:
        config = load_config(args.config)
    except (ConfigError, OSError) as exc:
        logger.error("config error: %s", exc)
        return 2

    state_path = Path(args.state)
    states = load_state(state_path)

    if args.command == "run-once":
        return run_cycle(config, states, args.dry_run, state_path)

    while True:
        run_cycle(config, states, args.dry_run, state_path)
        time.sleep(config.poll_interval_seconds)


if __name__ == "__main__":
    sys.exit(main())
