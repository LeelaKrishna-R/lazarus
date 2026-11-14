import pytest

from lazarus.checks import run_check
from lazarus.config import Check, ConfigError, Host, load_config
from lazarus.detection import INCIDENT_TYPES, check_key

MEMINFO = """MemTotal:        8000000 kB
MemFree:          200000 kB
MemAvailable:     800000 kB
Buffers:          100000 kB
"""


def host():
    return Host(name="h", address="10.0.0.1", ssh_user="ops", checks=[])


def test_over_the_limit_is_not_ok():
    res = run_check(
        host(),
        Check(type="memory", max_percent=85),
        runners={"memory": lambda a, u, c, t: (0, MEMINFO)},
    )
    assert res.ok is False
    assert res.detail == {"used_percent": 90, "max_percent": 85}


def test_under_the_limit_is_ok_and_reads_proc_meminfo():
    seen = {}

    def runner(address, user, command, timeout):
        seen["command"] = command
        return (0, MEMINFO)

    res = run_check(host(), Check(type="memory", max_percent=95), runners={"memory": runner})
    assert res.ok is True and seen["command"] == "cat /proc/meminfo"


def test_unreadable_output_is_a_failure():
    res = run_check(
        host(), Check(type="memory"), runners={"memory": lambda a, u, c, t: (0, "nope")}
    )
    assert res.ok is False and res.error


def test_incident_type_and_key():
    assert INCIDENT_TYPES["memory"] == "memory_high"
    assert check_key(Check(type="memory")) == "memory:"


def test_config(tmp_path):
    p = tmp_path / "c.yaml"
    p.write_text(
        "hosts:\n  - name: h\n    address: 10.0.0.1\n    checks:\n      - type: memory\n        max_percent: 80\n"
    )
    assert load_config(p).hosts[0].checks[0].max_percent == 80.0
    p.write_text(
        "hosts:\n  - name: h\n    address: 10.0.0.1\n    checks:\n      - type: memory\n        max_percent: 0\n"
    )
    with pytest.raises(ConfigError):
        load_config(p)
