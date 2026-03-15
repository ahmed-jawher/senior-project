import json
from pathlib import Path

import duckdb

from logconsolidator.config.defaults import PROCESSED_OUTPUT_PATH
from logconsolidator.output.base import OutputAdapter
from logconsolidator.process.models import LogEntry
import logging

logger = logging.getLogger(__name__)

class StorageAdapter(OutputAdapter):
    """Writes processed entries into DuckDB for durable local storage."""

    def __init__(self, output_path: Path = PROCESSED_OUTPUT_PATH) -> None:
        self.output_path = output_path
        self.output_path.parent.mkdir(parents=True, exist_ok=True)

        self.con = duckdb.connect(str(self.output_path))
        self._init_schema()

    def _init_schema(self) -> None:
        self.con.execute("""
            CREATE TABLE IF NOT EXISTS logs (
                source_id VARCHAR,
                observed_at TIMESTAMP,
                raw_message VARCHAR,
                fields_json VARCHAR
            );
        """)

    def handle(self, entry: LogEntry) -> None:
        payload = {
            "source_id": entry.source_id,
            "observed_at": entry.observed_at.isoformat(),
            "raw_message": entry.raw_message,
            **entry.fields,
        }

        fields_json = json.dumps(payload, ensure_ascii=False)

        self.con.execute(
            "INSERT INTO logs VALUES (?, ?, ?, ?)",
            [
                entry.source_id,
                entry.observed_at,
                entry.raw_message,
                fields_json,
            ],
        )
        logger.info("Stored log: %s", entry.raw_message)

    def close(self) -> None:
        self.con.close()