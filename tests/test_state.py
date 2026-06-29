import json

from lazarus.checks import CheckResult
from lazarus.detection import HostState, Incident
from lazarus.state import load_state, write_state


def test_write_state_is_readable(tmp_path):
    path = tmp_path / "state.json"
    st = HostState(name="web", status="healthy", confirmed_ok={"reachable:80": True})
    results = {"web": [CheckResult(type="reachable", ok=True, latency_ms=12.0)]}
    write_state(path, {"web": st}, results, "2026-06-29T00:00:00Z")
    data = json.loads(path.read_text())
    assert data["timestamp"] == "2026-06-29T00:00:00Z"
    assert data["hosts"][0]["name"] == "web"
    assert data["hosts"][0]["status"] == "healthy"
    assert data["hosts"][0]["checks"][0]["ok"] is True


def test_load_state_restores_status_and_incidents(tmp_path):
    path = tmp_path / "state.json"
    st = HostState(name="web", status="down", confirmed_ok={"reachable:80": False})
    st.incidents["reachable:80"] = Incident(
        host="web",
        type="host_unreachable",
        check_key="reachable:80",
        target="80",
        opened_at=1.0,
        attempts=2,
        last_attempt=5.0,
    )
    write_state(
        path,
        {"web": st},
        {"web": [CheckResult(type="reachable", ok=False)]},
        "2026-06-29T00:00:00Z",
    )

    restored = load_state(path)
    assert restored["web"].status == "down"
    assert restored["web"].confirmed_ok["reachable:80"] is False
    assert restored["web"].incidents["reachable:80"].attempts == 2
    assert restored["web"].incidents["reachable:80"].last_attempt == 5.0


def test_load_state_restores_pending_streak(tmp_path):
    path = tmp_path / "state.json"
    st = HostState(name="web", status="healthy", pending={"reachable:80": 1})
    write_state(path, {"web": st}, {"web": []}, "2026-06-29T00:00:00Z")
    restored = load_state(path)
    assert restored["web"].pending == {"reachable:80": 1}


def test_load_state_missing_file_returns_empty(tmp_path):
    assert load_state(tmp_path / "nope.json") == {}
