import json
import logging

import psycopg

from logconsolidator.output.base import OutputAdapter
from logconsolidator.process.models import LogEntry

logger = logging.getLogger(__name__)


class StorageAdapter(OutputAdapter):
    def __init__(self) -> None:
        self.conn = psycopg.connect(
            host="localhost",
            port=5432,
            dbname="logconsolidator",
            user="postgres",
            password="hero",
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