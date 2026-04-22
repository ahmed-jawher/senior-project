import json
import logging
import os

import psycopg

from logconsolidator.output.base import OutputAdapter
from logconsolidator.process.models import LogEntry

logger = logging.getLogger(__name__)


class StorageAdapter(OutputAdapter):
    def __init__(self) -> None:
        self.conn = psycopg.connect(
            host=os.environ.get("PGHOST", "localhost"),
            port=int(os.environ.get("PGPORT", "5432")),
            dbname=os.environ.get("PGDATABASE", "logconsolidator"),
            user=os.environ.get("PGUSER", "postgres"),
            password=os.environ.get("PGPASSWORD", ""),
        )
        self.conn.autocommit = True

    def handle(self, entry: LogEntry) -> None:
        payload = {
            "source_id": entry.source_id,
            "observed_at": entry.observed_at.isoformat(),
            "raw_message": entry.raw_message,
            **entry.fields,
        }

        with self.conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO logs (source_id, observed_at, raw_message, fields_json)
                VALUES (%s, %s, %s, %s::jsonb)
                """,
                (
                    entry.source_id,
                    entry.observed_at,
                    entry.raw_message,
                    json.dumps(payload, ensure_ascii=False),
                ),
            )

        logger.info("Stored log in PostgreSQL: %s", entry.raw_message)

    def close(self) -> None:
        self.conn.close()