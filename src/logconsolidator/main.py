from __future__ import annotations

"""Application orchestrator for the ingest -> process -> output pipeline."""

from datetime import datetime, timezone
import logging
from pathlib import Path
import queue
import signal
import sys
import threading
import time
from types import FrameType

# Support direct execution via `python3 src/logconsolidator/main.py` in a src-layout project.
if __package__ in {None, ""}:
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from logconsolidator.config.defaults import (
    POLL_INTERVAL_SECONDS,
    PROCESSED_QUEUE_MAXSIZE,
    QUEUE_GET_TIMEOUT_SECONDS,
    QUEUE_PUT_TIMEOUT_SECONDS,
    RAW_QUEUE_MAXSIZE,
    STATE_PATH,
)
import logconsolidator.config as config
import logconsolidator.core as core
import logconsolidator.ingest as ingest
import logconsolidator.output as output
import logconsolidator.process as process


class ProcessorWorker(threading.Thread):
    """Consumes raw lines, parses them, then pushes to both DuckDB and vector queues."""

    def __init__(
        self,
        raw_queue: queue.Queue[process.RawLogLine],
        processed_queue: queue.Queue[process.LogEntry],
        vector_queue: queue.Queue[process.LogEntry],
        parser: process.RegexParserRouter,
        stop_event: threading.Event,
    ) -> None:
        super().__init__(name="processor", daemon=True)
        self.raw_queue = raw_queue
        self.processed_queue = processed_queue
        self.vector_queue = vector_queue
        self.parser = parser
        self.stop_event = stop_event

    def run(self) -> None:
        while not self.stop_event.is_set():
            try:
                raw_line = self.raw_queue.get(timeout=QUEUE_GET_TIMEOUT_SECONDS)
            except queue.Empty:
                continue

            fields = self.parser.parse(raw_line)
            entry = process.LogEntry(
                source_id=raw_line.source_id,
                timestamp=fields.get("timestamp", datetime.now(timezone.utc).isoformat()),
                raw_message=raw_line.line,
                fields=fields,
            )
            # -:- Fan out to both queues. Each has its own worker draining at its own pace.
            self._put_with_backpressure(self.processed_queue, entry)
            self._put_with_backpressure(self.vector_queue, entry)
            self.raw_queue.task_done()

    def _put_with_backpressure(self, q: queue.Queue, entry: process.LogEntry) -> None:
        while not self.stop_event.is_set():
            try:
                q.put(entry, timeout=QUEUE_PUT_TIMEOUT_SECONDS)
                return
            except queue.Full:
                continue


class DispatcherWorker(threading.Thread):
    """Drains the processed queue and writes to DuckDB via StorageAdapter."""

    def __init__(
        self,
        processed_queue: queue.Queue[process.LogEntry],
        adapters: list[output.OutputAdapter],
        stop_event: threading.Event,
        logger: logging.Logger,
    ) -> None:
        super().__init__(name="dispatcher", daemon=True)
        self.processed_queue = processed_queue
        self.adapters = adapters
        self.stop_event = stop_event
        self.logger = logger

    def run(self) -> None:
        while not self.stop_event.is_set():
            try:
                entry = self.processed_queue.get(timeout=QUEUE_GET_TIMEOUT_SECONDS)
            except queue.Empty:
                continue

            for adapter in self.adapters:
                try:
                    adapter.handle(entry)
                except Exception as exc:  # pragma: no cover
                    self.logger.exception("adapter '%s' failed: %s", adapter.__class__.__name__, exc)

            self.processed_queue.task_done()


class VectorWorker(threading.Thread):
    """Dedicated thread for ChromaDB writes, drains the vector queue independently."""

    def __init__(
        self,
        vector_queue: queue.Queue[process.LogEntry],
        adapter: output.VectorAdapter,
        stop_event: threading.Event,
        logger: logging.Logger,
    ) -> None:
        super().__init__(name="vector-worker", daemon=True)
        self.vector_queue = vector_queue
        self.adapter = adapter
        self.stop_event = stop_event
        self.logger = logger

    def run(self) -> None:
        while not self.stop_event.is_set():
            try:
                entry = self.vector_queue.get(timeout=QUEUE_GET_TIMEOUT_SECONDS)
            except queue.Empty:
                continue

            try:
                self.adapter.handle(entry)
            except Exception as exc:  # pragma: no cover
                self.logger.exception("VectorAdapter failed: %s", exc)

            self.vector_queue.task_done()


class LogConsolidatorApp:
    """Builds and manages worker threads, queues, state, and output adapters."""

    def __init__(self) -> None:
        self.logger = core.configure_logging()
        self.stop_event = threading.Event()
        self.queues = core.PipelineQueues(
            raw_size=RAW_QUEUE_MAXSIZE,
            processed_size=PROCESSED_QUEUE_MAXSIZE,
        )
        self.state_store = ingest.PositionStateStore(STATE_PATH)
        self.watchers: list[ingest.FileWatcher] = []
        self.processor: ProcessorWorker | None = None
        self.dispatcher: DispatcherWorker | None = None
        self.vector_worker: VectorWorker | None = None
        self.adapters: list[output.OutputAdapter] = []

    def start(self) -> None:
        # -:- 1) Load source definitions and compile parser routes once at startup.
        sources = config.load_sources()
        parser = process.RegexParserRouter(sources)

        # -:- 2) Create one watcher per source; each watcher tails its own file.
        self.watchers = [
            ingest.FileWatcher(
                source=source,
                raw_queue=self.queues.raw_queue,
                state_store=self.state_store,
                stop_event=self.stop_event,
                poll_interval=POLL_INTERVAL_SECONDS,
            )
            for source in sources
        ]

        # -:- 3) Processor fans out parsed entries to both queues.
        self.processor = ProcessorWorker(
            raw_queue=self.queues.raw_queue,
            processed_queue=self.queues.processed_queue,
            vector_queue=self.queues.vector_queue,
            parser=parser,
            stop_event=self.stop_event,
        )

        # -:- 4) DuckDB dispatcher — fast, drains processed_queue independently.
        storage_adapter = output.StorageAdapter(sources=sources)
        self.adapters = [storage_adapter]
        self.dispatcher = DispatcherWorker(
            processed_queue=self.queues.processed_queue,
            adapters=self.adapters,
            stop_event=self.stop_event,
            logger=self.logger,
        )

        # -:- 5) ChromaDB worker — slow, drains vector_queue independently.
        vector_adapter = output.VectorAdapter()
        self.adapters.append(vector_adapter)
        self.vector_worker = VectorWorker(
            vector_queue=self.queues.vector_queue,
            adapter=vector_adapter,
            stop_event=self.stop_event,
            logger=self.logger,
        )

        for watcher in self.watchers:
            watcher.start()
        self.processor.start()
        self.dispatcher.start()
        self.vector_worker.start()

        self.logger.info("pipeline started: watchers=%d", len(self.watchers))

    def stop(self) -> None:
        self.stop_event.set()

        for watcher in self.watchers:
            watcher.join(timeout=2)

        if self.processor is not None:
            self.processor.join(timeout=2)

        if self.dispatcher is not None:
            self.dispatcher.join(timeout=2)

        if self.vector_worker is not None:
            self.vector_worker.join(timeout=5)

        for adapter in self.adapters:
            adapter.close()

        self.logger.info("pipeline stopped")


def run() -> None:
    """CLI entrypoint with signal handling and graceful shutdown."""
    app = LogConsolidatorApp()

    def _handle_signal(_signum: int, _frame: FrameType | None) -> None:
        app.stop_event.set()

    signal.signal(signal.SIGINT, _handle_signal)
    signal.signal(signal.SIGTERM, _handle_signal)

    try:
        app.start()
    except core.ConfigError as exc:
        app.logger.error("configuration error: %s", exc)
        return

    try:
        while not app.stop_event.is_set():
            time.sleep(0.5)
    except KeyboardInterrupt:
        app.stop_event.set()
    finally:
        app.stop()


if __name__ == "__main__":
    run()
