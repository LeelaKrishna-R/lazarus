import io
import json

from lazarus import cli
from lazarus.metrics import render


def _state(tmp_path, data):
    path = tmp_path / "state.json"
    path.write_text(json.dumps(data))
    return path


def _samples(text):
    return [line for line in text.splitlines() if line and not line.startswith("#")]


def test_metrics_from_the_last_poll(tmp_path):
    path = _state(
        tmp_path,
        {
            "timestamp": "2026-11-18T07:00:00Z",
            "hosts": [
                {
                    "name": "web",
                    "status": "down",
                    "open_incidents": [
                        {"type": "service_down", "attempts": 2},
                        {"type": "service_down", "attempts": 1},
                        {"type": "disk_full", "attempts": 0},
                    ],
                },
                {"name": "db", "status": "healthy", "open_incidents": []},
            ],
        },
    )
    out = io.StringIO()
    assert cli.show_metrics(path, out) == 0
    assert _samples(out.getvalue()) == [
        "lazarus_state_readable 1",
        "lazarus_last_poll_timestamp_seconds 1794985200",
        'lazarus_host_healthy{host="web"} 0',
        'lazarus_host_healthy{host="db"} 1',
        'lazarus_open_incidents{host="web",type="disk_full"} 1',
        'lazarus_open_incidents{host="web",type="service_down"} 2',
        'lazarus_remediation_attempts{host="web",type="disk_full"} 0',
        'lazarus_remediation_attempts{host="web",type="service_down"} 3',
    ]


def test_every_metric_has_help_and_type():
    state = {"timestamp": "2026-11-18T07:00:00Z", "hosts": [{"name": "web", "status": "healthy"}]}
    text = render(state)
    names = {line.split()[0].split("{")[0] for line in _samples(text)}
    for name in names:
        assert f"# HELP {name} " in text and f"# TYPE {name} gauge" in text


def test_label_values_are_escaped():
    text = render({"hosts": [{"name": 'we"b\\1', "status": "healthy"}]})
    assert 'lazarus_host_healthy{host="we\\"b\\\\1"} 1' in text


def test_an_unreadable_state_is_said_not_dropped(tmp_path):
    for content in (None, "{not json", json.dumps({"timestamp": "x"})):
        path = tmp_path / "state.json"
        path.unlink(missing_ok=True)
        if content is not None:
            path.write_text(content)
        out = io.StringIO()
        assert cli.show_metrics(path, out) == 2
        assert _samples(out.getvalue()) == ["lazarus_state_readable 0"]


def test_a_timestamp_that_isnt_one_leaves_the_poll_time_out():
    text = render({"timestamp": "yesterday", "hosts": []})
    assert "lazarus_last_poll_timestamp_seconds" not in text
    assert "lazarus_state_readable 1" in text


def test_metrics_needs_no_config(tmp_path):
    path = _state(tmp_path, {"timestamp": "2026-11-18T07:00:00Z", "hosts": []})
    assert cli.main(["metrics", "--state", str(path)]) == 0


def test_a_fractional_poll_time_keeps_its_precision():
    text = render({"timestamp": "2026-11-18T07:00:00.250000Z", "hosts": []})
    assert "lazarus_last_poll_timestamp_seconds 1794985200.25" in text
