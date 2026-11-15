import pytest

from lazarus.checks import run_check
from lazarus.config import Check, ConfigError, Host, load_config
from lazarus.detection import INCIDENT_TYPES, check_key

OUT = "3.90 2.10 1.50 2/310 4412\n4\n"  # /proc/loadavg, then nproc


def host():
    return Host(name="h", address="10.0.0.1", ssh_user="ops", checks=[])


def test_load_per_core_over_the_limit_is_not_ok():
    res = run_check(
        host(), Check(type="load", max_percent=50), runners={"load": lambda a, u, c, t: (0, OUT)}
    )
    assert res.ok is False
    assert res.detail == {"load_5m": 2.1, "cores": 4, "used_percent": 52, "max_percent": 50}


def test_it_reads_loadavg_and_nproc_and_judges_the_5_minute_average():
    seen = {}

    def runner(address, user, command, timeout):
        seen["command"] = command
        return (0, OUT)

    res = run_check(host(), Check(type="load", max_percent=50), runners={"load": runner})
    assert seen["command"] == "cat /proc/loadavg; nproc"
    assert res.detail["used_percent"] == 52 and res.ok is False  # 2.10 over 4 cores
    assert (
        run_check(host(), Check(type="load", max_percent=60), runners={"load": runner}).ok is True
    )


def test_unreadable_output_is_a_failure():
    res = run_check(host(), Check(type="load"), runners={"load": lambda a, u, c, t: (0, "nope")})
    assert res.ok is False and res.error and res.unknown is True


def test_incident_and_config(tmp_path):
    assert INCIDENT_TYPES["load"] == "load_high" and check_key(Check(type="load")) == "load:"
    head = "hosts:\n  - name: h\n    address: 10.0.0.1\n    checks:\n"
    p = tmp_path / "c.yaml"
    p.write_text(head + "      - type: load\n        max_percent: 150\n")
    with pytest.raises(ConfigError):
        load_config(p)
    p.write_text(head + "      - type: load\n")
    assert load_config(p).hosts[0].checks[0].max_percent == 90.0
