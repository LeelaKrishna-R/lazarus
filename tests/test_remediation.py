from lazarus.config import Host, Remediation
from lazarus.detection import Incident
from lazarus.remediation import find_rule, remediate, should_remediate


def incident(itype="service_down", target="friday"):
    return Incident(host="h", type=itype, check_key="service:friday", target=target, opened_at=0.0)


def host_with_rule(**kw):
    rule = Remediation(on="service_down", action="systemctl restart friday", service="friday", **kw)
    return Host(name="h", address="1.1.1.1", checks=[], remediation=[rule]), rule


def test_find_rule_matches_type_and_service():
    host, rule = host_with_rule()
    assert find_rule(host, incident()) is rule


def test_find_rule_no_match_returns_none():
    host, _ = host_with_rule()
    assert find_rule(host, incident(itype="http_unhealthy")) is None


def test_should_remediate_blocks_after_max_attempts():
    _, rule = host_with_rule(max_attempts=2)
    inc = incident()
    inc.attempts = 2
    assert should_remediate(inc, rule, now=1000.0) is False


def test_should_remediate_respects_cooldown():
    _, rule = host_with_rule(max_attempts=5, cooldown_seconds=300.0)
    inc = incident()
    inc.attempts = 1
    inc.last_attempt = 1000.0
    assert should_remediate(inc, rule, now=1100.0) is False
    assert should_remediate(inc, rule, now=1400.0) is True


def test_remediate_dry_run_executes_nothing_and_does_not_count():
    host, rule = host_with_rule()
    inc = incident()
    calls = []
    res = remediate(host, inc, rule, now=1.0, dry_run=True, runner=lambda *a: calls.append(a))
    assert res.executed is False
    assert calls == []
    assert inc.attempts == 0


def test_remediate_executes_and_counts():
    host, rule = host_with_rule()
    inc = incident()
    res = remediate(
        host,
        inc,
        rule,
        now=5.0,
        dry_run=False,
        runner=lambda address, user, command, timeout: (0, "ok"),
    )
    assert res.executed is True
    assert inc.attempts == 1
    assert inc.last_attempt == 5.0
