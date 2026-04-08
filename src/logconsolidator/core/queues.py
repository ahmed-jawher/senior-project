from __future__ import annotations

import queue

from logconsolidator.config.defaults import VECTOR_QUEUE_MAXSIZE
from logconsolidator.process.models import LogEntry, RawLogLine


class PipelineQueues:
    """Owns bounded queues that connect ingest, process, and dispatch stages."""

    def __init__(self, raw_size: int, processed_size: int, vector_size: int = VECTOR_QUEUE_MAXSIZE) -> None:
        # -:- raw_queue: watcher -> processor, processed_queue: processor -> dispatcher.
        self.raw_queue: queue.Queue[RawLogLine] = queue.Queue(maxsize=raw_size)
        self.processed_queue: queue.Queue[LogEntry] = queue.Queue(maxsize=processed_size)
        # -:- vector_queue: processor -> vector worker (separate thread for ChromaDB).
        self.vector_queue: queue.Queue[LogEntry] = queue.Queue(maxsize=vector_size)
