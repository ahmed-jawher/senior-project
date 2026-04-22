from __future__ import annotations

from datetime import datetime, time, timedelta, timezone
import logging
import threading
from typing import Optional

from logconsolidator.query.rag import RAGEngine
from logconsolidator.query.report_fetcher import ReportFetcher

logger = logging.getLogger(__name__)


class ReportScheduler(threading.Thread):
    """Daemon thread that generates the previous day's report at midnight UTC."""

    def __init__(
        self,
        engine: RAGEngine,
        fetcher: ReportFetcher,
        stop_event: Optional[threading.Event] = None,
    ) -> None:
        super().__init__(name="report-scheduler", daemon=True)
        self.engine = engine
        self.fetcher = fetcher
        self.stop_event = stop_event or threading.Event()

    def request_stop(self) -> None:
        self.stop_event.set()

    def run(self) -> None:
        logger.info("report scheduler started")
        while not self.stop_event.is_set():
            sleep_seconds = self._seconds_until_midnight()
            # -:- Event.wait returns True when set, False on timeout; either way re-check the loop.
            if self.stop_event.wait(timeout=sleep_seconds):
                break

            target_date = datetime.now(timezone.utc).date() - timedelta(days=1)
            try:
                self.engine.generate_report(self.fetcher, target_date)
            except Exception:  # pragma: no cover
                logger.exception("report generation failed for %s", target_date)
        logger.info("report scheduler stopped")

    def _seconds_until_midnight(self) -> float:
        now = datetime.now(timezone.utc)
        next_midnight = datetime.combine(
            now.date() + timedelta(days=1),
            time.min,
            tzinfo=timezone.utc,
        )
        delta = (next_midnight - now).total_seconds()
        # -:- Guarantee forward progress even if we somehow wake right on the boundary.
        return max(delta, 1.0)
