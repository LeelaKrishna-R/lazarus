from __future__ import annotations

import json
import logging
import urllib.request
from collections.abc import Callable

from lazarus.detection import Event

logger = logging.getLogger("lazarus.alerter")

WEBHOOK_TIMEOUT = 5.0


def format_alert(event: Event) -> dict:
    inc = event.incident
    verb = "RESOLVED" if event.kind == "closed" else "FIRING"
    label = f"{inc.host}: {inc.type}" + (f" ({inc.target})" if inc.target else "")
    return {
        "content": f"[{verb}] {label}",
        "host": inc.host,
        "type": inc.type,
        "target": inc.target,
        "state": event.kind,
    }


def _post(url: str, payload: dict, timeout: float) -> None:
    req = urllib.request.Request(
        url, data=json.dumps(payload).encode(), headers={"Content-Type": "application/json"}
    )
    with urllib.request.urlopen(req, timeout=timeout):
        pass


def send_alert(
    webhook: str | None, payload: dict, poster: Callable = _post, timeout: float = WEBHOOK_TIMEOUT
) -> bool:
    if not webhook:
        logger.warning("no webhook configured; skipping alert: %s", payload.get("content"))
        return False
    try:
        poster(webhook, payload, timeout)
        return True
    except Exception as exc:
        logger.warning("failed to post alert: %s", exc)
        return False
