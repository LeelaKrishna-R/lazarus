import pytest

from lazarus.checks import run_check
from lazarus.config import Check, ConfigError, Host, load_config
from lazarus.detection import INCIDENT_TYPES, check_key

DF = """Filesystem     1024-blocks      Used Available Capacity Mounted on
/dev/sda1         98831908  85995732   7786868      92% /
"""


def host():
    return Host(name="h", address="10.0.0.1", ssh_user="ops", checks=[])


def disk(**kw):
    return Check(type="disk", path=kw.pop("path", "/"), **kw)


def test_over_the_limit_is_not_ok():
    res = run_check(host(), disk(max_percent=90), runners={"disk": lambda a, u, c, t: (0, DF)})
    assert res.ok is False and res.unknown is False
    assert res.detail == {"path": "/", "used_percent": 92, "max_percent": 90}


def test_under_the_limit_is_ok():
    res = run_check(host(), disk(max_percent=95), runners={"disk": lambda a, u, c, t: (0, DF)})
    assert res.ok is True


def test_the_path_is_shell_quoted_and_df_is_portable():
    seen = {}

    def runner(address, user, command, timeout):
        seen["command"] = command
        return (0, DF)

    run_check(host(), disk(path="/mnt/my disk; rm -rf /"), runners={"disk": runner})
    assert seen["command"] == "df -P '/mnt/my disk; rm -rf /'"


def test_unreadable_output_is_a_failure_not_a_pass():
    res = run_check(
        host(), disk(), runners={"disk": lambda a, u, c, t: (1, "df: /nope: No such file")}
    )
    assert res.ok is False and res.error and res.unknown is True


def test_disk_incident_and_key():
    assert INCIDENT_TYPES["disk"] == "disk_full"
    assert check_key(disk(path="/var")) == "disk:/var"


def _write(tmp_path, check_yaml):
    p = tmp_path / "c.yaml"
    p.write_text("hosts:\n  - name: h\n    address: 10.0.0.1\n    checks:\n" + check_yaml)
    return p


def test_config_reads_a_disk_check(tmp_path):
    cfg = load_config(
        _write(tmp_path, "      - type: disk\n        path: /\n        max_percent: 85\n")
    )
    c = cfg.hosts[0].checks[0]
    assert (c.type, c.path, c.max_percent) == ("disk", "/", 85.0)


def test_config_defaults_and_bounds(tmp_path):
    cfg = load_config(_write(tmp_path, "      - type: disk\n        path: /\n"))
    assert cfg.hosts[0].checks[0].max_percent == 90.0
    with pytest.raises(ConfigError):
        load_config(
            _write(tmp_path, "      - type: disk\n        path: /\n        max_percent: 120\n")
        )
    with pytest.raises(ConfigError):
        load_config(_write(tmp_path, "      - type: disk\n"))


def test_ssh_failure_is_unknown_not_a_full_disk():
    def runner(address, user, command, timeout):
        raise OSError("ssh: Could not resolve hostname")

    res = run_check(host(), disk(), runners={"disk": runner})
    assert res.ok is False and res.unknown is True and "resolve" in res.error
