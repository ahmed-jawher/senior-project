from __future__ import annotations

"""Application orchestrator for the ingest -> process -> output pipeline."""

from datetime import datetime, timezone
import logging
import queue
import signal
import threading
import time
from types import FrameType

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
    """Consumes raw lines, parses them, then pushes normalized entries forward."""

    def __init__(
        self,
        raw_queue: queue.Queue[process.RawLogLine],
        processed_queue: queue.Queue[process.LogEntry],
        parser: process.RegexParserRouter,
        stop_event: threading.Event,
    ) -> None:
        super().__init__(name="processor", daemon=True)
        self.raw_queue = raw_queue
        self.processed_queue = processed_queue
        self.parser = parser
        self.stop_event = stop_event

    def run(self) -> None:
        # -:- Keep pulling raw lines until shutdown is requested.
        while not self.stop_event.is_set():
            try:
                raw_line = self.raw_queue.get(timeout=QUEUE_GET_TIMEOUT_SECONDS)
            except queue.Empty:
                continue

            # -:- Attach processing metadata and parser output to build a LogEntry.
            fields = self.parser.parse(raw_line)
            entry = process.LogEntry(
                source_id=raw_line.source_id,
                observed_at=datetime.now(timezone.utc),
                raw_message=raw_line.line,
                fields=fields,
            )
            self._put_with_backpressure(entry)
            self.raw_queue.task_done()

    def _put_with_backpressure(self, entry: process.LogEntry) -> None:
        # -:- Retry while queue is full so bursts do not drop data.
        while not self.stop_event.is_set():
            try:
                self.processed_queue.put(entry, timeout=QUEUE_PUT_TIMEOUT_SECONDS)
                return
            except queue.Full:
                continue


class DispatcherWorker(threading.Thread):
    """Fans out processed entries to all configured output adapters."""

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
        # -:- Pull processed entries and dispatch each one to every sink.
        while not self.stop_event.is_set():
            try:
                entry = self.processed_queue.get(timeout=QUEUE_GET_TIMEOUT_SECONDS)
            except queue.Empty:
                continue

            for adapter in self.adapters:
                try:
                    adapter.handle(entry)
                # -:- One adapter failure is isolated and should not stop the pipeline.
                except Exception as exc:  # pragma: no cover
                    self.logger.exception("adapter '%s' failed: %s", adapter.__class__.__name__, exc)

            self.processed_queue.task_done()


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

        # -:- 3) Start the central processor that converts raw lines to LogEntry.
        self.processor = ProcessorWorker(
            raw_queue=self.queues.raw_queue,
            processed_queue=self.queues.processed_queue,
            parser=parser,
            stop_event=self.stop_event,
        )

        # -:- 4) Register output sinks and start dispatcher for fan-out delivery.
        self.adapters = [output.StorageAdapter(), output.VectorAdapter()]
        self.dispatcher = DispatcherWorker(
            processed_queue=self.queues.processed_queue,
            adapters=self.adapters,
            stop_event=self.stop_event,
            logger=self.logger,
        )

        for watcher in self.watchers:
            watcher.start()
        self.processor.start()
        self.dispatcher.start()

        self.logger.info("pipeline started: watchers=%d", len(self.watchers))

    def stop(self) -> None:
        # -:- Signal all threads first, then join and close adapters cleanly.
        self.stop_event.set()

        for watcher in self.watchers:
            watcher.join(timeout=2)

        if self.processor is not None:
            self.processor.join(timeout=2)

        if self.dispatcher is not None:
            self.dispatcher.join(timeout=2)

        for adapter in self.adapters:
            adapter.close()

        self.logger.info("pipeline stopped")


def run() -> None:
    """CLI entrypoint with signal handling and graceful shutdown."""
    app = LogConsolidatorApp()

    def _handle_signal(_signum: int, _frame: FrameType | None) -> None:
        # -:- SIGINT/SIGTERM both trigger the same cooperative shutdown flag.
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
