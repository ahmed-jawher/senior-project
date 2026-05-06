import json
import logging
import os

import psycopg

from logconsolidator.output.base import OutputAdapter
from logconsolidator.process.models import LogEntry

logger = logging.getLogger(__name__)


class StorageAdapter(OutputAdapter):
    """Persists processed log entries to PostgreSQL with one-shot reconnect on transient failures."""

    def __init__(self) -> None:
        self._conn_kwargs = {
            "host": os.environ.get("PGHOST", "localhost"),
            "port": int(os.environ.get("PGPORT", "5432")),
            "dbname": os.environ.get("PGDATABASE", "logconsolidator"),
            "user": os.environ.get("PGUSER", "postgres"),
            "password": os.environ.get("PGPASSWORD", ""),
        }
        self.conn: psycopg.Connection | None = None
        self._connect()

    def _connect(self) -> None:
        self.conn = psycopg.connect(**self._conn_kwargs)
        self.conn.autocommit = True

    def handle(self, entry: LogEntry) -> None:
        try:
            self._insert(entry)
        except psycopg.OperationalError as exc:
            # Connection died (DB restart, network blip). Try once to reconnect; if
            # that also fails, propagate so the dispatcher logs and drops the line
            # rather than killing the worker.
            logger.warning("postgres insert failed (%s); reconnecting", exc)
            self._safe_close()
            self._connect()
            self._insert(entry)

    def _insert(self, entry: LogEntry) -> None:
        assert self.conn is not None
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
                    json.dumps(entry.fields, ensure_ascii=False),
                ),
            )
        logger.debug("stored log: source=%s", entry.source_id)

    def _safe_close(self) -> None:
        if self.conn is None:
            return
        try:
            self.conn.close()
        except Exception:
            pass
        self.conn = None

    def close(self) -> None:
        self._safe_close()
