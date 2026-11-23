import subprocess

import pytest

from lazarus import checks
from lazarus.config import ConfigError, load_config


def write(tmp_path, text):
    p = tmp_path / "config.yaml"
    p.write_text(text)
    return p


HOST = """
hosts:
  - name: nas
    address: 10.0.0.5
    ssh_user: admin
    {port}
    checks:
      - type: disk
        path: /
"""


def test_ssh_port_is_read_and_checked(tmp_path):
    assert (
        load_config(write(tmp_path, HOST.format(port="ssh_port: 2222"))).hosts[0].ssh_port == 2222
    )
    assert load_config(write(tmp_path, HOST.format(port=""))).hosts[0].ssh_port is None
    for bad in ("ssh_port: 0", "ssh_port: 70000", "ssh_port: twenty-two"):
        with pytest.raises(ConfigError, match="ssh_port"):
            load_config(write(tmp_path, HOST.format(port=bad)))


def test_ssh_run_passes_the_port_only_when_set(monkeypatch):
    seen = []

    def run(cmd, **kw):
        seen.append(cmd)
        return subprocess.CompletedProcess(cmd, 0, stdout="ok", stderr="")

    monkeypatch.setattr(checks.subprocess, "run", run)
    checks.ssh_run("10.0.0.5", "admin", "uptime", 5, port=2222)
    checks.ssh_run("10.0.0.5", None, "uptime", 5)
    assert seen[0] == ["ssh", "-o", "BatchMode=yes", "-p", "2222", "admin@10.0.0.5", "uptime"]
    assert seen[1] == ["ssh", "-o", "BatchMode=yes", "10.0.0.5", "uptime"]


def test_a_disk_check_reaches_the_host_on_its_ssh_port(tmp_path):
    host = load_config(write(tmp_path, HOST.format(port="ssh_port: 2222"))).hosts[0]
    calls = []

    def runner(address, user, command, timeout, **kw):
        calls.append(kw)
        return (
            0,
            "Filesystem 1024-blocks Used Available Capacity Mounted on\n/dev/sda1 100 40 60 40% /",
        )

    result = checks.run_check(host, host.checks[0], {"disk": runner})
    assert result.ok and calls == [{"port": 2222}]
