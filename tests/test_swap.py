from lazarus.checks import run_check
from lazarus.config import Check, Host
from lazarus.detection import INCIDENT_TYPES


def meminfo(total, free):
    return (
        "MemTotal:        8000000 kB\nMemAvailable:    4000000 kB\n"
        f"SwapTotal:  {total} kB\nSwapFree:   {free} kB\n"
    )


def host():
    return Host(name="h", address="10.0.0.1", ssh_user="ops", checks=[])


def run(text, max_percent=50, code=0):
    check = Check(type="swap", max_percent=max_percent)
    return run_check(host(), check, runners={"swap": lambda a, u, c, t: (code, text)})


def test_swap_past_the_limit_is_not_ok():
    res = run(meminfo(2000000, 600000))
    assert res.ok is False and res.detail == {"used_percent": 70, "max_percent": 50}


def test_swap_under_the_limit_is_ok():
    assert run(meminfo(2000000, 1800000)).ok is True


def test_no_swap_is_fine_and_says_so():
    res = run(meminfo(0, 0))
    assert res.ok is True and res.detail == {"swap": "none"}


def test_unreadable_output_is_a_failure_not_a_pass():
    assert run("MemTotal: 8000000 kB\n").ok is False
    assert run("", code=1).ok is False


def test_it_opens_a_swap_high_incident():
    assert INCIDENT_TYPES["swap"] == "swap_high"


def test_no_reading_is_unknown_so_it_opens_no_incident():
    assert run("MemTotal: 8000000 kB\n").unknown is True
    assert run("", code=1).unknown is True
    assert run(meminfo(2000000, 600000)).unknown is False
