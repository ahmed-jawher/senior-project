import json
import threading
from pathlib import Path

from logconsolidator.config.defaults import PROCESSED_OUTPUT_PATH
from logconsolidator.output.base import OutputAdapter
from logconsolidator.process.models import LogEntry


class StorageAdapter(OutputAdapter):
    def __init__(self, output_path: Path = PROCESSED_OUTPUT_PATH) -> None:
        self.output_path = output_path
        self.output_path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.Lock()

    def handle(self, entry: LogEntry) -> None:
        payload = {
            "source_id": entry.source_id,
            "observed_at": entry.observed_at.isoformat(),
            "severity": entry.severity.value,
            "raw_message": entry.raw_message,
            **entry.fields,
        }
        with self._lock:
            with self.output_path.open("a", encoding="utf-8") as handle:
                handle.write(json.dumps(payload) + "\n")
