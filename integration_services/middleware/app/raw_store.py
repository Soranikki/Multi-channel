import json
import os
from pathlib import Path
from threading import Lock
from typing import Any


class JsonlEventStore:
    def __init__(self, store_dir: str) -> None:
        self.store_dir = Path(store_dir)
        self.store_dir.mkdir(parents=True, exist_ok=True)
        self._lock = Lock()

    def append(self, filename: str, record: dict[str, Any]) -> None:
        path = self.store_dir / filename
        with self._lock, path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(record, ensure_ascii=False) + "\n")

    def read(self, filename: str, limit: int = 100) -> list[dict[str, Any]]:
        path = self.store_dir / filename
        if not path.exists():
            return []
        with self._lock, path.open("r", encoding="utf-8") as handle:
            lines = handle.readlines()[-limit:]
        return [json.loads(line) for line in lines if line.strip()]


def build_store() -> JsonlEventStore:
    return JsonlEventStore(os.getenv("EVENT_STORE_DIR", "/data"))
