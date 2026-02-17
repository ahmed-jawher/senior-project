import queue
import signal
import threading
import time

from logconsolidator.config.defaults import (
    POLL_INTERVAL_SECONDS,
    PROCESSED_QUEUE_MAXSIZE,
    QUEUE_GET_TIMEOUT_SECONDS,
    QUEUE_PUT_TIMEOUT_SECONDS,
    RAW_QUEUE_MAXSIZE,
    STATE_PATH,
)
from logconsolidator.config.loader import load_sources
from logconsolidator.core.exceptions import ConfigError
from logconsolidator.core.logging import configure_logging
from logconsolidator.core.queues import PipelineQueues
from logconsolidator.ingest.state import PositionStateStore
from logconsolidator.ingest.watcher import FileWatcher
from logconsolidator.output.base import OutputAdapter
from logconsolidator.output.storage import StorageAdapter
from logconsolidator.output.vector import VectorAdapter
from logconsolidator.process.models import LogEntry, RawLogLine
from logconsolidator.process.normalizer import LogNormalizer
from logconsolidator.process.parser import RegexParserRouter


class ProcessorWorker(threading.Thread):
    def __init__(
        self,
        raw_queue: "queue.Queue[RawLogLine]",
        processed_queue: "queue.Queue[LogEntry]",
        parser: RegexParserRouter,
        normalizer: LogNormalizer,
        stop_event: threading.Event,
    ) -> None:
        super().__init__(name="processor", daemon=True)
        self.raw_queue = raw_queue
        self.processed_queue = processed_queue
        self.parser = parser
        self.normalizer = normalizer
        self.stop_event = stop_event

    def run(self) -> None:
        while not self.stop_event.is_set():
            try:
                raw_line = self.raw_queue.get(timeout=QUEUE_GET_TIMEOUT_SECONDS)
            except queue.Empty:
                continue

            fields = self.parser.parse(raw_line)
            entry = self.normalizer.normalize(raw_line, fields)
            self._put_with_backpressure(entry)
            self.raw_queue.task_done()

    def _put_with_backpressure(self, entry: LogEntry) -> None:
        while not self.stop_event.is_set():
            try:
                self.processed_queue.put(entry, timeout=QUEUE_PUT_TIMEOUT_SECONDS)
                return
            except queue.Full:
                continue


class DispatcherWorker(threading.Thread):
    def __init__(
        self,
        processed_queue: "queue.Queue[LogEntry]",
        adapters: list[OutputAdapter],
        stop_event: threading.Event,
        logger_name: str,
    ) -> None:
        super().__init__(name="dispatcher", daemon=True)
        self.processed_queue = processed_queue
        self.adapters = adapters
        self.stop_event = stop_event
        self.logger_name = logger_name

    def run(self) -> None:
        import logging

        logger = logging.getLogger(self.logger_name)
        while not self.stop_event.is_set():
            try:
                entry = self.processed_queue.get(timeout=QUEUE_GET_TIMEOUT_SECONDS)
            except queue.Empty:
                continue

            for adapter in self.adapters:
                try:
                    adapter.handle(entry)
                except Exception as exc:  # pragma: no cover
                    logger.exception("adapter '%s' failed: %s", adapter.__class__.__name__, exc)

            self.processed_queue.task_done()


class LogConsolidatorApp:
    def __init__(self) -> None:
        self.logger = configure_logging()
        self.stop_event = threading.Event()
        self.queues = PipelineQueues(
            raw_size=RAW_QUEUE_MAXSIZE,
            processed_size=PROCESSED_QUEUE_MAXSIZE,
        )
        self.state_store = PositionStateStore(STATE_PATH)
        self.watchers: list[FileWatcher] = []
        self.processor: ProcessorWorker | None = None
        self.dispatcher: DispatcherWorker | None = None
        self.adapters: list[OutputAdapter] = []

    def start(self) -> None:
        sources = load_sources()
        parser = RegexParserRouter(sources)
        normalizer = LogNormalizer()

        self.watchers = [
            FileWatcher(
                source=source,
                raw_queue=self.queues.raw_queue,
                state_store=self.state_store,
                stop_event=self.stop_event,
                poll_interval=POLL_INTERVAL_SECONDS,
            )
            for source in sources
        ]

        self.processor = ProcessorWorker(
            raw_queue=self.queues.raw_queue,
            processed_queue=self.queues.processed_queue,
            parser=parser,
            normalizer=normalizer,
            stop_event=self.stop_event,
        )

        self.adapters = [StorageAdapter(), VectorAdapter()]
        self.dispatcher = DispatcherWorker(
            processed_queue=self.queues.processed_queue,
            adapters=self.adapters,
            stop_event=self.stop_event,
            logger_name=self.logger.name,
        )

        for watcher in self.watchers:
            watcher.start()
        self.processor.start()
        self.dispatcher.start()

        self.logger.info("pipeline started: watchers=%d", len(self.watchers))

    def stop(self) -> None:
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
    app = LogConsolidatorApp()

    def _handle_signal(_signum: int, _frame: object) -> None:
        app.stop()

    signal.signal(signal.SIGINT, _handle_signal)
    signal.signal(signal.SIGTERM, _handle_signal)

    try:
        app.start()
    except ConfigError as exc:
        app.logger.error("configuration error: %s", exc)
        return

    try:
        while not app.stop_event.is_set():
            time.sleep(0.5)
    except KeyboardInterrupt:
        app.stop()
