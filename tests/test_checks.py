from lazarus.checks import run_check
from lazarus.config import Check, Host


def host(addr="10.0.0.1"):
    return Host(name="h", address=addr, checks=[])


def test_reachable_ok():
    def runner(address, port, timeout):
        assert (address, port, timeout) == ("10.0.0.1", 80, 5.0)

    res = run_check(host(), Check(type="reachable", port=80), runners={"reachable": runner})
    assert res.ok is True
    assert res.type == "reachable"


def test_reachable_failure_is_not_ok():
    def runner(address, port, timeout):
        raise OSError("connection refused")

    res = run_check(host(), Check(type="reachable", port=80), runners={"reachable": runner})
    assert res.ok is False
    assert "refused" in res.error


def test_reachable_timeout_is_not_ok():
    def runner(address, port, timeout):
        raise TimeoutError("timed out")

    res = run_check(host(), Check(type="reachable", port=80), runners={"reachable": runner})
    assert res.ok is False
    assert res.error


def test_http_health_2xx_ok():
    res = run_check(
        host(),
        Check(type="http_health", url="http://x/health"),
        runners={"http_health": lambda url, timeout: 200},
    )
    assert res.ok is True
    assert res.detail["status_code"] == 200


def test_http_health_500_not_ok():
    res = run_check(
        host(),
        Check(type="http_health", url="http://x/health"),
        runners={"http_health": lambda url, timeout: 500},
    )
    assert res.ok is False


def test_service_active_ok():
    def runner(address, user, command, timeout):
        assert "systemctl is-active friday" in command
        return (0, "active")

    res = run_check(host(), Check(type="service", name="friday"), runners={"service": runner})
    assert res.ok is True


def test_service_inactive_not_ok():
    res = run_check(
        host(),
        Check(type="service", name="friday"),
        runners={"service": lambda address, user, command, timeout: (3, "inactive")},
    )
    assert res.ok is False
