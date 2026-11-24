import textwrap

import pytest

from lazarus.config import Config, ConfigError, load_config


def write(tmp_path, text):
    p = tmp_path / "config.yaml"
    p.write_text(textwrap.dedent(text))
    return p


def test_loads_minimal_config(tmp_path):
    p = write(
        tmp_path,
        """
        hosts:
          - name: web
            address: 10.0.0.1
            checks:
              - type: reachable
                port: 80
    """,
    )
    cfg = load_config(p)
    assert isinstance(cfg, Config)
    assert cfg.poll_interval_seconds == 60.0
    assert cfg.debounce == 2
    host = cfg.hosts[0]
    assert host.name == "web"
    assert host.checks[0].type == "reachable"
    assert host.checks[0].port == 80
    assert host.checks[0].timeout_seconds == 5.0


def test_expands_env_in_webhook(tmp_path, monkeypatch):
    monkeypatch.setenv("HOOK", "https://example.com/hook")
    p = write(
        tmp_path,
        """
        alerting:
          webhook: ${HOOK}
        hosts:
          - name: web
            address: 10.0.0.1
            checks:
              - type: reachable
                port: 80
    """,
    )
    cfg = load_config(p)
    assert cfg.alerting.webhook == "https://example.com/hook"


def test_missing_webhook_env_disables_alerting_without_failing(tmp_path, monkeypatch):
    monkeypatch.delenv("MISSING_HOOK", raising=False)
    p = write(
        tmp_path,
        """
        alerting:
          webhook: ${MISSING_HOOK}
        hosts:
          - name: web
            address: 10.0.0.1
            checks:
              - type: reachable
                port: 80
    """,
    )
    cfg = load_config(p)
    assert cfg.alerting.webhook is None


def test_rejects_unknown_check_type(tmp_path):
    p = write(
        tmp_path,
        """
        hosts:
          - name: web
            address: 10.0.0.1
            checks:
              - type: telepathy
    """,
    )
    with pytest.raises(ConfigError, match="unknown check type"):
        load_config(p)


def test_service_check_requires_name(tmp_path):
    p = write(
        tmp_path,
        """
        hosts:
          - name: web
            address: 10.0.0.1
            checks:
              - type: service
    """,
    )
    with pytest.raises(ConfigError, match="service check requires"):
        load_config(p)


def test_remediation_on_key_survives_yaml_bool_quirk(tmp_path):
    p = write(
        tmp_path,
        """
        hosts:
          - name: web
            address: 10.0.0.1
            checks:
              - type: service
                name: friday
            remediation:
              - on: service_down
                action: systemctl restart friday
    """,
    )
    cfg = load_config(p)
    assert cfg.hosts[0].remediation[0].on == "service_down"
    assert cfg.hosts[0].remediation[0].action == "systemctl restart friday"


def test_rejects_non_positive_timeout(tmp_path):
    p = write(
        tmp_path,
        """
        hosts:
          - name: web
            address: 10.0.0.1
            checks:
              - type: reachable
                port: 80
                timeout_seconds: 0
    """,
    )
    with pytest.raises(ConfigError, match="timeout_seconds"):
        load_config(p)


def test_rejects_non_numeric_timeout(tmp_path):
    p = write(
        tmp_path,
        """
        hosts:
          - name: web
            address: 10.0.0.1
            checks:
              - type: reachable
                port: 80
                timeout_seconds: soon
    """,
    )
    with pytest.raises(ConfigError, match="timeout_seconds"):
        load_config(p)


def test_rejects_non_positive_poll_interval(tmp_path):
    p = write(
        tmp_path,
        """
        poll_interval_seconds: -5
        hosts:
          - name: web
            address: 10.0.0.1
            checks:
              - type: reachable
                port: 80
    """,
    )
    with pytest.raises(ConfigError, match="poll_interval_seconds"):
        load_config(p)


def test_rejects_debounce_below_one(tmp_path):
    p = write(
        tmp_path,
        """
        debounce: 0
        hosts:
          - name: web
            address: 10.0.0.1
            checks:
              - type: reachable
                port: 80
    """,
    )
    with pytest.raises(ConfigError, match="debounce"):
        load_config(p)


def test_rejects_negative_cooldown(tmp_path):
    p = write(
        tmp_path,
        """
        hosts:
          - name: web
            address: 10.0.0.1
            checks:
              - type: reachable
                port: 80
            remediation:
              - on: service_down
                action: systemctl restart x
                cooldown_seconds: -1
    """,
    )
    with pytest.raises(ConfigError, match="cooldown_seconds"):
        load_config(p)


def test_host_with_no_checks_is_rejected(tmp_path):
    p = write(
        tmp_path,
        """
        hosts:
          - name: web
            address: 10.0.0.1
    """,
    )
    with pytest.raises(ConfigError, match="no checks"):
        load_config(p)


def _remediating(tmp_path, on, check="service"):
    extra = "\n        name: web" if check == "service" else ""
    path = tmp_path / "c.yaml"
    path.write_text(
        f"""
hosts:
  - name: web
    address: 10.0.0.5
    checks:
      - type: {check}{extra}
    remediation:
      - on: {on}
        action: "systemctl restart web"
"""
    )
    return path


def test_a_remediation_on_an_incident_that_doesnt_exist_is_refused(tmp_path):
    with pytest.raises(ConfigError, match="remediation 'on' must be one of .*got 'service_dwn'"):
        load_config(_remediating(tmp_path, "service_dwn"))


def test_a_remediation_no_check_on_the_host_can_open_is_refused(tmp_path):
    with pytest.raises(ConfigError, match="remediation on 'disk_full' can never run"):
        load_config(_remediating(tmp_path, "disk_full"))


def test_a_remediation_its_check_opens_loads(tmp_path):
    cfg = load_config(_remediating(tmp_path, "service_down"))
    assert cfg.hosts[0].remediation[0].on == "service_down"


def test_expect_status_one_code_or_a_list(tmp_path):
    def cfg(line):
        return write(
            tmp_path,
            f"""
        hosts:
          - name: web
            address: 10.0.0.1
            checks:
              - type: http_health
                url: http://10.0.0.1/health
                {line}
        """,
        )

    assert load_config(cfg("expect_status: 401")).hosts[0].checks[0].expect_status == (401,)
    assert load_config(cfg("expect_status: [200, 401]")).hosts[0].checks[0].expect_status == (
        200,
        401,
    )
    assert load_config(cfg("")).hosts[0].checks[0].expect_status is None
    for bad in ("expect_status: ok", "expect_status: 42", "expect_status: []"):
        with pytest.raises(ConfigError, match="expect_status"):
            load_config(cfg(bad))
