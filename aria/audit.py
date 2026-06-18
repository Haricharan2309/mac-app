"""A small, local-first action log.

The brief (Sections 9 and 7) makes action logging a safety requirement, not a
nicety: an agent that can drive your machine needs an audit trail. Phase 0 is
read-only, but the trail is also the most useful debugging aid for the live
voice path — you can see exactly what Aria heard as intent and what it did.

Entries are appended as JSON Lines to a local file the user owns and can delete
(local-first privacy posture). When no path is configured, entries are kept in
memory only (used by tests) and nothing is written.
"""

from __future__ import annotations

import json
import threading
import time
from pathlib import Path
from typing import Optional


class ActionLog:
    def __init__(self, path: Optional[str] = None) -> None:
        self.path = Path(path).expanduser() if path else None
        self.entries: list[dict] = []
        self._lock = threading.Lock()
        if self.path is not None:
            self.path.parent.mkdir(parents=True, exist_ok=True)

    def record(self, kind: str, **fields) -> dict:
        entry = {"ts": round(time.time(), 3), "kind": kind, **fields}
        self.entries.append(entry)
        if self.path is not None:
            line = json.dumps(entry, ensure_ascii=False)
            with self._lock:
                with self.path.open("a", encoding="utf-8") as f:
                    f.write(line + "\n")
        return entry
