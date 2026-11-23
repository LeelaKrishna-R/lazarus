import lazarus


def test_package_imports():
    assert lazarus.__name__ == "lazarus"


def test_python_dash_m_runs_the_cli(tmp_path):
    import os
    import subprocess
    import sys

    env = {**os.environ, "PYTHONPATH": os.pathsep.join(sys.path)}
    state = str(tmp_path / "none.json")
    done = subprocess.run(
        [sys.executable, "-m", "lazarus", "status", "--state", state],
        capture_output=True,
        text=True,
        env=env,
    )
    assert done.returncode == 2 and f"no state at {state}" in done.stdout
