from __future__ import annotations

from datetime import date as date_type, datetime, time, timedelta
import json
import os
from typing import Any, Dict, List

import psycopg


class ReportFetcher:
    """Queries PostgreSQL for log rows within one UTC calendar day."""

    def __init__(self, connection_factory=None) -> None:
        # -:- Factory indirection keeps tests able to inject a fake connection.
        self._connection_factory = connection_factory or self._default_connection_factory

    @staticmethod
    def _default_connection_factory():
        return psycopg.connect(
            host=os.environ.get("PGHOST", "localhost"),
            port=int(os.environ.get("PGPORT", "5432")),
            dbname=os.environ.get("PGDATABASE", "logconsolidator"),
            user=os.environ.get("PGUSER", "postgres"),
            password=os.environ.get("PGPASSWORD", ""),
        )

    def fetch_last_24h(self, target_date: date_type) -> List[Dict[str, Any]]:
        # -:- Compare against naive datetimes; schema stores observed_at as TIMESTAMP.
        start = datetime.combine(target_date, time.min)
        end = start + timedelta(days=1)

        conn = self._connection_factory()
        try:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    SELECT source_id, observed_at, raw_message, fields_json
                    FROM logs
                    WHERE observed_at >= %s AND observed_at < %s
                    ORDER BY observed_at ASC
                    """,
                    (start, end),
                )
                rows = cur.fetchall()
        finally:
            conn.close()

        return [
            {
                "source_id": row[0],
                "observed_at": row[1],
                "raw_message": row[2],
                "fields_json": self._normalize_fields(row[3]),
            }
            for row in rows
        ]

    @staticmethod
    def _normalize_fields(value: Any) -> str:
        # -:- psycopg returns JSONB as a dict; downstream context builder expects a string.
        if value is None:
            return ""
        if isinstance(value, str):
            return value
        return json.dumps(value, ensure_ascii=False)
