import json
import threading
from pathlib import Path
from logconsolidator.config.defaults import PROCESSED_OUTPUT_PATH
from logconsolidator.output.base import OutputAdapter
from logconsolidator.process.models import LogEntry


class StorageAdapter(OutputAdapter):
    """Writes processed entries as JSON Lines for durable local storage."""

    def __init__(self, output_path: Path = PROCESSED_OUTPUT_PATH) -> None:
        self.output_path = output_path
        # -:- Ensure parent folder exists before first write.
        self.output_path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.Lock()

    def handle(self, entry: LogEntry) -> None:
        # -:- Flatten structured fields into one JSON object per output line.
        payload = {
            "source_id": entry.source_id,
            "timestamp": entry.timestamp,
            "raw_message": entry.raw_message,
            **entry.fields,
        }
        # -:- Lock keeps writes from multiple threads serialized and line-safe.
        with self._lock:
            with self.output_path.open("a", encoding="utf-8") as handle:
                handle.write(json.dumps(payload) + "\n")
