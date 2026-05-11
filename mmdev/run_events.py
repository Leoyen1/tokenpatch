from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


RUN_EVENTS_FILE = "run-events.jsonl"


def append_run_event(mmdev_dir: Path, event: dict[str, Any]) -> Path:
    path = mmdev_dir / "logs" / RUN_EVENTS_FILE
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = {"ts": datetime.now(timezone.utc).isoformat(), **event}
    with path.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(payload, ensure_ascii=False) + "\n")
    return path

