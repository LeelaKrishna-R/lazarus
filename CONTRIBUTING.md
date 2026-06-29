# Contributing

Thanks for your interest in lazarus.

## Setup

```bash
git clone <repo-url>
cd lazarus
python -m venv .venv
.venv/Scripts/python -m pip install -e ".[dev]"   # Linux/macOS: .venv/bin/...
```

## Before opening a PR

```bash
.venv/Scripts/python -m pytest        # all tests pass (no real hosts needed)
.venv/Scripts/ruff check src tests    # lint clean
.venv/Scripts/ruff format src tests   # formatted
```

Tests use fakes for all network and SSH calls, so the suite runs anywhere with
no servers. Keep it that way: new logic should be tested through injected
runners, not live connections.

Keep changes focused and within the v0.1 scope (see the README's "what it
doesn't" section). Larger ideas are welcome as issues first.
