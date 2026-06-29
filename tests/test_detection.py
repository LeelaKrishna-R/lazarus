from lazarus.checks import CheckResult
from lazarus.config import Check
from lazarus.detection import HostState, check_key, evaluate


def reachable(port=80):
    return Check(type="reachable", port=port)


def service(name="friday"):
    return Check(type="service", name=name)


def ok(check):
    return (check, CheckResult(type=check.type, ok=True))


def fail(check):
    return (check, CheckResult(type=check.type, ok=False))


def test_single_failure_does_not_flip_with_debounce_2():
    st = HostState(name="h")
    assert evaluate(st, [fail(reachable())], debounce=2, now=0.0) == []
    assert st.status == "healthy"


def test_two_consecutive_failures_open_incident_and_mark_down():
    st = HostState(name="h")
    chk = reachable()
    evaluate(st, [fail(chk)], debounce=2, now=0.0)
    events = evaluate(st, [fail(chk)], debounce=2, now=1.0)
    assert len(events) == 1
    assert events[0].kind == "opened"
    assert events[0].incident.type == "host_unreachable"
    assert st.status == "down"


def test_recovery_closes_incident():
    st = HostState(name="h")
    chk = reachable()
    evaluate(st, [fail(chk)], debounce=2, now=0.0)
    evaluate(st, [fail(chk)], debounce=2, now=1.0)
    evaluate(st, [ok(chk)], debounce=2, now=2.0)
    events = evaluate(st, [ok(chk)], debounce=2, now=3.0)
    assert len(events) == 1
    assert events[0].kind == "closed"
    assert st.status == "healthy"
    assert st.incidents == {}


def test_service_failure_is_degraded_not_down():
    st = HostState(name="h")
    chk = service()
    evaluate(st, [fail(chk)], debounce=1, now=0.0)
    assert st.status == "degraded"
    assert st.incidents[check_key(chk)].type == "service_down"
    assert st.incidents[check_key(chk)].target == "friday"


def test_intermittent_failure_resets_pending():
    st = HostState(name="h")
    chk = reachable()
    evaluate(st, [fail(chk)], debounce=2, now=0.0)
    evaluate(st, [ok(chk)], debounce=2, now=1.0)
    assert evaluate(st, [fail(chk)], debounce=2, now=2.0) == []
    assert st.status == "healthy"
