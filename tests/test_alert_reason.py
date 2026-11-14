from lazarus.alerter import format_alert
from lazarus.checks import CheckResult
from lazarus.config import Check
from lazarus.detection import Event, HostState, Incident, evaluate


def opened(check, result):
    events = evaluate(HostState(name="nas"), [(check, result)], debounce=1, now=0.0)
    assert [e.kind for e in events] == ["opened"]
    return events[0]


def test_a_full_disk_says_how_full():
    ev = opened(
        Check(type="disk", path="/"),
        CheckResult(
            type="disk", ok=False, detail={"path": "/", "used_percent": 92, "max_percent": 90.0}
        ),
    )
    assert ev.incident.reason == "92% used, limit 90%"
    assert format_alert(ev)["content"] == "[FIRING] nas: disk_full (/): 92% used, limit 90%"


def test_an_unhealthy_endpoint_says_its_status():
    ev = opened(
        Check(type="http_health", url="http://nas/health"),
        CheckResult(type="http_health", ok=False, detail={"status_code": 503}),
    )
    assert format_alert(ev)["reason"] == "HTTP 503"


def test_an_unreachable_host_says_the_error_and_a_stopped_service_its_state():
    ev = opened(
        Check(type="reachable", port=22), CheckResult(type="reachable", ok=False, error="timed out")
    )
    assert ev.incident.reason == "timed out"
    ev = opened(
        Check(type="service", name="smbd"),
        CheckResult(type="service", ok=False, detail={"name": "smbd", "output": "inactive"}),
    )
    assert ev.incident.reason == "inactive"


def test_resolved_alerts_and_old_saved_incidents_stay_as_they_were():
    inc = Incident(
        host="nas", type="service_down", check_key="service:smbd", target="smbd", opened_at=0.0
    )
    assert inc.reason is None
    assert format_alert(Event("closed", inc))["content"] == "[RESOLVED] nas: service_down (smbd)"
