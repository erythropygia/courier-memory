"""Token kullanım günlüğü: JSON Lines dosyasına satır ekler (CM_USAGE_LOG, varsayılan data/usage.jsonl)."""
from __future__ import annotations

import json
from pathlib import Path


class FileUsageSink:
    def __init__(self, path: Path):
        self.path = Path(path)

    def record(self, row: dict) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self.path.open("a", encoding="utf-8") as f:
            f.write(json.dumps(row) + "\n")
