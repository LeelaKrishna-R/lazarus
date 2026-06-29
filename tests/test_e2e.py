import textwrap

from lazarus import checks, cli, remediation
from lazarus.config import load_config


def test_down_remediate_recover_closes(tmp_path, monkeypatch):
    cfg_path = tmp_path / "config.yaml"
    cfg_path.write_text(
        textwrap.dedent("""
        debounce: 1
        hosts:
          - name: web
            address: 10.0.0.1
            checks:
              - type: service
                name: friday
            remediation:
              - on: service_down
                service: friday
                action: systemctl restart friday
                max_attempts: 2
                cooldown_seconds: 0
    """)
    )
    config = load_config(cfg_path)
    state_path = tmp_path / "state.json"

    service_ok = {"value": False}
    remediations = []
    alerts = []

    monkeypatch.setattr(
        cli,
        "run_check",
        lambda host, check, runners=None: checks.CheckResult(
            type="service", ok=service_ok["value"], detail={"name": check.name}
        ),
    )
    monkeypatch.setattr(
        cli, "send_alert", lambda webhook, payload, **k: alerts.append(payload) or True
    )
    monkeypatch.setattr(
        remediation,
        "ssh_run",
        lambda address, user, command, timeout: remediations.append(command) or (0, "ok"),
    )

    clock = {"t": 0.0}

    def now():
        clock["t"] += 1.0
        return clock["t"]

    states = {}
    code = cli.run_cycle(config, states, dry_run=False, state_path=state_path, now_fn=now)
    assert code == 1
    assert states["web"].status == "degraded"
    assert remediations == ["systemctl restart friday"]
    assert any(a["state"] == "opened" for a in alerts)

    service_ok["value"] = True
    code = cli.run_cycle(config, states, dry_run=False, state_path=state_path, now_fn=now)
    assert code == 0
    assert states["web"].status == "healthy"
    assert any(a["state"] == "closed" for a in alerts)
