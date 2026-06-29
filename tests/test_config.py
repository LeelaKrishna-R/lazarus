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
