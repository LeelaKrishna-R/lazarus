import io
import json

import pytest

from lazarus import cli


def _state(tmp_path, hosts):
    path = tmp_path / "state.json"
    path.write_text(json.dumps({"timestamp": "2026-11-18T07:00:00Z", "hosts": hosts}))
    return path


def test_status_lists_hosts_and_open_incidents(tmp_path):
    path = _state(
        tmp_path,
        [
            {
                "name": "web",
                "status": "down",
                "open_incidents": [
                    {
                        "host": "web",
                        "type": "service_down",
                        "check_key": "service:friday",
                        "target": "friday",
                        "opened_at": 1795000000.0,
                        "attempts": 2,
                        "reason": "inactive",
                    }
                ],
            },
            {"name": "db", "status": "healthy", "open_incidents": []},
        ],
    )
    out = io.StringIO()
    assert cli.show_status(path, out) == 1
    text = out.getvalue()
    assert "last poll: 2026-11-18T07:00:00Z" in text
    assert "web: down" in text and "db: healthy" in text
    assert "open service_down (friday): inactive since 2026-11-18" in text
    assert "2 remediation attempt(s)" in text


def test_status_all_healthy_exits_zero(tmp_path):
    path = _state(tmp_path, [{"name": "web", "status": "healthy", "open_incidents": []}])
    assert cli.show_status(path, io.StringIO()) == 0


@pytest.mark.parametrize("content, said", [(None, "no state at"), ("{not json", "can't read")])
def test_status_without_a_readable_state_says_so(tmp_path, content, said):
    path = tmp_path / "state.json"
    if content is not None:
        path.write_text(content)
    out = io.StringIO()
    assert cli.show_status(path, out) == 2
    assert said in out.getvalue()


def test_status_needs_no_config(tmp_path, capsys):
    path = _state(tmp_path, [{"name": "web", "status": "healthy", "open_incidents": []}])
    assert cli.main(["status", "--state", str(path)]) == 0


def test_run_once_still_needs_a_config():
    with pytest.raises(SystemExit):
        cli.main(["run-once"])
