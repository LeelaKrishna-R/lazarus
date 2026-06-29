from lazarus.alerter import format_alert, send_alert
from lazarus.detection import Event, Incident


def event(kind="opened"):
    inc = Incident(
        host="web", type="service_down", check_key="service:friday", target="friday", opened_at=0.0
    )
    return Event(kind, inc)


def test_format_alert_firing():
    payload = format_alert(event("opened"))
    assert payload["state"] == "opened"
    assert "web" in payload["content"]
    assert "service_down" in payload["content"]


def test_send_alert_no_webhook_returns_false():
    sent = []
    assert send_alert(None, {"content": "x"}, poster=lambda *a: sent.append(a)) is False
    assert sent == []


def test_send_alert_posts_when_webhook_set():
    sent = []

    def poster(url, payload, timeout):
        sent.append(url)

    assert send_alert("http://hook", {"content": "x"}, poster=poster) is True
    assert sent == ["http://hook"]
