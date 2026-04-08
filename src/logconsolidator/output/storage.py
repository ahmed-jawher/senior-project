from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

import duckdb

from logconsolidator.config.defaults import PROCESSED_OUTPUT_PATH
from logconsolidator.config.models import WatchSourceConfig
from logconsolidator.output.base import OutputAdapter
from logconsolidator.process.models import LogEntry


class StorageAdapter(OutputAdapter):
    """Writes processed entries into DuckDB with dynamic columns from source configs."""

    def __init__(self, sources: list[WatchSourceConfig], output_path: Path = PROCESSED_OUTPUT_PATH) -> None:
        self.output_path = output_path
        self.output_path.parent.mkdir(parents=True, exist_ok=True)

        # -:- Collect all unique field names across all sources for dynamic columns.
        self.field_names: list[str] = sorted(
            {field for source in sources for field in source.parser.patterns}
        )

        self.con = duckdb.connect(str(self.output_path))
        self._init_schema()

    def _init_schema(self) -> None:
        field_cols = "".join(f",\n                {name} VARCHAR" for name in self.field_names)
        self.con.execute(f"""
            CREATE TABLE IF NOT EXISTS logs (
                observed_at TIMESTAMP,
                source_id VARCHAR,
                raw_message VARCHAR{field_cols}
            );
        """)

    def handle(self, entry: LogEntry) -> None:
        placeholders = ", ".join(["?"] * (3 + len(self.field_names)))
        columns = ", ".join(["observed_at", "source_id", "raw_message"] + self.field_names)
        values = [datetime.now(timezone.utc), entry.source_id, entry.raw_message] + [
            entry.fields.get(name) for name in self.field_names
        ]

        self.con.execute(f"INSERT INTO logs ({columns}) VALUES ({placeholders})", values)

    def close(self) -> None:
        self.con.close()
