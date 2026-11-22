import io

from lazarus import cli


def _write(tmp_path, text):
    path = tmp_path / "config.yaml"
    path.write_text(text)
    return str(path)


GOOD = """
poll_interval_seconds: 30
hosts:
  - name: web
    address: web.example.com
    checks:
      - type: reachable
        port: 443
      - type: service
        name: nginx
    remediation:
      - on: service_down
        service: nginx
        action: "systemctl restart nginx"
"""


def test_a_valid_config_is_summarised_and_exits_0(tmp_path):
    out = io.StringIO()
    assert cli.check_config(_write(tmp_path, GOOD), out) == 0
    lines = out.getvalue().splitlines()
    assert lines[0] == (
        "config ok: 1 host(s), 2 check(s), 1 remediation(s), poll every 30s, debounce 2"
    )
    assert lines[1] == "no alerting webhook: state changes are only logged"


def test_an_invalid_config_says_why_and_exits_2(tmp_path):
    # no disk check on this host opens disk_full, so the remediation could never run
    bad = GOOD.replace("on: service_down", "on: disk_full")
    out = io.StringIO()
    assert cli.check_config(_write(tmp_path, bad), out) == 2
    assert out.getvalue().startswith("config error: ")


def test_a_missing_file_exits_2(tmp_path):
    out = io.StringIO()
    assert cli.check_config(str(tmp_path / "nope.yaml"), out) == 2


def test_check_config_runs_from_the_command_line(tmp_path, capsys):
    assert cli.main(["check-config", "--config", _write(tmp_path, GOOD)]) == 0
    assert capsys.readouterr().out.startswith("config ok: 1 host(s)")
