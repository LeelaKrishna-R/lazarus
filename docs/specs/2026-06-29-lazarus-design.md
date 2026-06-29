# lazarus — v0.1 Design Spec

- **Date:** 2026-06-29
- **Status:** Approved (design green-lit in chat)
- **Repo:** `lazarus` (own git repo; lives in the workspace alongside `net-triage`)

## Summary

`lazarus` is a Python CLI/daemon that monitors a list of hosts defined in a YAML
config, folds per-host checks into a health status with flap-debounce, runs
whitelisted remediation actions under hard safety limits, alerts on state changes
via webhook, and persists a JSON state snapshot each cycle (restored on startup).
It extracts the self-healing "immune system" pattern from the author's Friday
system into a standalone, installable tool a stranger can point at their own homelab.

One-liner: *self-healing monitor for homelab/edge infra — detects failures,
auto-remediates a whitelist, alerts.*

## Goals

- Detect host/service/network failures from a declarative YAML config.
- Auto-remediate the simple cases **safely** (whitelist + hard limits + dry-run).
- Be trivially installable and testable on a laptop with no real infrastructure.
- Be a clean cron/monitoring citizen (exit-code contract, atomic state, logging).

## Non-goals (out of scope for v0.1 — binding)

Web dashboard, auth/login, multi-user, metrics database (Prometheus/Grafana),
distributed/HA, plugin system, fancy notification routing. **PyPI publish is
deferred** (installable via `pipx` / `pip install git+…`; publish only on request).
Anything beyond scope goes in the README roadmap, not the code.

## Stack & dependencies (deliberately tiny)

- **Python 3.11+**
- **Runtime dependency: `PyYAML` only.** Everything else is stdlib:
  - `socket` (TCP reachability), `urllib` (HTTP health + webhook POST),
    `subprocess` (SSH via the system `ssh` binary — uses the user's `~/.ssh`),
    `json`, `dataclasses`, `logging`, `time`/`datetime`, `pathlib`, `os`, `argparse`.
- **Dev dependencies: `pytest`, `ruff`** (ruff = lint *and* format; `lint` runs `ruff check` + `ruff format --check`).
- **Packaging:** `pyproject.toml` (setuptools), `src/` layout, console script
  `lazarus = lazarus.cli:main`.
- **License:** MIT.

No new dependency is added without explicit approval.

## Architecture (modules under `src/lazarus/`)

Each module has one job; functions stay small and single-purpose.

- **`config.py`** — load + validate YAML into typed dataclasses
  (`Config`, `Host`, `Check`, `Remediation`, `Alerting`). Raise a clear
  `ConfigError` on invalid input. Resolve `${ENV_VAR}` references (e.g. the
  webhook URL) from the environment.
- **`checks.py`** — three check functions returning a structured `CheckResult`
  (`type`, `ok`, detail fields, `latency_ms`, `error`):
  - `reachable` — TCP connect, **explicit timeout**.
  - `http_health` — GET, 2xx = ok, **explicit timeout**.
  - `service` — `ssh <host> systemctl is-active <svc>`, **explicit timeout**.

  Each check accepts an **injectable runner/transport** so tests use fakes (no
  real sockets/SSH).
- **`detection.py`** — fold the latest `CheckResult`s for a host into a status
  (`healthy` / `degraded` / `down`) with **flap-debounce** (status flips only
  after N consecutive identical outcomes, default 2). Track per-(host, check)
  failure streaks; open/close incidents; emit `IncidentOpened` / `IncidentClosed`
  events carrying an incident **type** (`host_unreachable`, `http_unhealthy`,
  `service_down`) used to match remediation rules.
- **`remediation.py`** — for an open incident, find the matching whitelisted rule
  (by `on:` type + target), enforce `max_attempts` and `cooldown_seconds`, and
  execute the action over SSH (subprocess, **with timeout**). Honors global
  `--dry-run`: log the intended command, execute nothing. Returns a
  `RemediationResult`.
- **`alerter.py`** — format a structured message and POST it to the webhook
  (urllib, **with timeout**) on incident open/close (state changes only, never
  every cycle). Discord-compatible (`content` field) plus structured fields.
  No-op with a logged warning if no webhook is configured.
- **`state.py`** — serialize full monitor state (per-host status, open incidents,
  failure streaks, remediation attempt counts + last-attempt timestamps) to JSON.
  **Atomic write** (temp file + `os.replace`). Read on startup to restore so
  state survives restarts.
- **`cli.py`** — `argparse` with subcommands `run-once` and `daemon`;
  `--config PATH`; `--dry-run`. Configures `logging`. Orchestrates each cycle:
  checks → detection → remediation → alerter → state.

## Status model

- `healthy` — all checks for the host pass.
- `degraded` — host reachable, but ≥1 non-reachability check (http/service)
  failing past debounce.
- `down` — reachability check failing past debounce.

Status changes only after `debounce` consecutive identical results (default 2),
so a single blip causes no noise.

## Incident & remediation model

- An incident is keyed by (host, check identity) and carries a derived `type`
  (`host_unreachable` / `http_unhealthy` / `service_down`).
- Remediation rules in config match incidents by `on:` (incident type) + target
  (e.g. service name).
- On a matching **open** incident: if `attempts < max_attempts` and
  `now − last_attempt ≥ cooldown_seconds`, execute the action (or log it under
  `--dry-run`), increment attempts, stamp `last_attempt`.
- Attempt counts reset when the incident **closes** (recovery).
- Restart-loops are impossible: `max_attempts` caps total tries per incident;
  `cooldown` spaces them.

## Safety (README headline — maturity signal)

Remediation runs real commands over SSH, so it's deliberately fenced:
**whitelist-only actions per host**, **`max_attempts` + `cooldown`** to make
restart-loops impossible, and **`--dry-run`** to exercise the whole pipeline
touching nothing. Framing: "constrained autonomy."

## Timeouts (hard requirement)

Every external interaction has an explicit timeout — TCP connect, HTTP request,
SSH command (subprocess), webhook POST. A single hung host must never stall the
poll cycle. Timeouts have sane defaults (e.g. 5s) and may be overridden per check.

## Logging

stdlib `logging` throughout: INFO for cycle summaries and state changes, WARNING
for check failures / missing webhook, DEBUG for per-check detail. `--dry-run`
logs intended remediation commands. No `print()` for runtime output.

## Data shapes

**`config.yaml`** (per-check `timeout_seconds` added to the plan-doc shape):

```yaml
poll_interval_seconds: 60
alerting:
  webhook: ${DISCORD_WEBHOOK_URL}
hosts:
  - name: friday-nuc
    address: friday.krishnar.xyz
    checks:
      - type: reachable
        port: 7777
        timeout_seconds: 5
      - type: http_health
        url: https://friday.krishnar.xyz/health
        timeout_seconds: 5
      - type: service
        name: friday
        via: ssh            # uses ssh user/key from config or ~/.ssh
        timeout_seconds: 10
    remediation:
      - on: service_down
        service: friday
        action: "systemctl restart friday"
        max_attempts: 2
        cooldown_seconds: 300
```

**`state.json`:**

```json
{
  "timestamp": "2026-06-29T14:32:00Z",
  "hosts": [
    {
      "name": "friday-nuc",
      "status": "healthy",
      "checks": [
        { "type": "reachable", "ok": true, "latency_ms": 12 },
        { "type": "http_health", "ok": true, "status_code": 200 },
        { "type": "service", "name": "friday", "ok": true }
      ],
      "open_incidents": []
    }
  ]
}
```

## CLI

- `lazarus run-once --config config.yaml [--dry-run]`
- `lazarus daemon --config config.yaml [--dry-run]`

**Exit codes:** `0` = all hosts healthy · `1` = one or more open incidents ·
`2` = config/usage error. (Applies to `run-once` and to startup validation;
`daemon` loops until interrupted.)

## Testing (`pytest`)

All network/SSH goes through injectable fakes — the suite runs on a laptop with
no real hosts or servers and opens no sockets.

- **Unit:** config validation; check result-folding incl. the timeout path
  (fake runners); detection (debounce thresholds, status transitions, incident
  open/close); remediation (whitelist match, `max_attempts`, `cooldown`, dry-run).
- **E2E:** a fake host transitions **down → remediation fires → recovers →
  incident closes**, asserting state transitions, attempt accounting, and that an
  alert would be posted. Driven through the `cli` orchestration with fakes.

Type hints on all signatures/dataclasses. `ruff check` + `ruff format` clean.

## Repo layout

```
lazarus/
  src/lazarus/
    __init__.py  config.py  checks.py  detection.py
    remediation.py  alerter.py  state.py  cli.py
  tests/
    test_config.py  test_checks.py  test_detection.py
    test_remediation.py  test_state.py  test_e2e.py
  examples/config.yaml
  docs/specs/2026-06-29-lazarus-design.md
  README.md  LICENSE  CONTRIBUTING.md  SECURITY.md
  pyproject.toml  .gitignore  CLAUDE.md
```

## Build order (one focused, test-first step each)

1. `pyproject` + package skeleton + ruff/pytest config; `config.py` + tests.
2. `checks.py` (three checkers, injectable runners, timeouts) + tests.
3. `detection.py` (status fold, debounce, incidents) + tests.
4. `remediation.py` (whitelist, `max_attempts`, `cooldown`, dry-run) + tests.
5. `alerter.py` + `state.py` (atomic write/read) + tests.
6. `cli.py` (run-once/daemon, logging, orchestration) + e2e test.
7. README + LICENSE + CONTRIBUTING + SECURITY + example config + demo GIF.

## Roadmap (README only — not built in v0.1)

Prometheus exporter, more check types (disk/CPU thresholds), read-only web status
page, pluggable remediation handlers, async polling, pydantic config, mypy.
