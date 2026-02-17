from pathlib import Path
import json
import queue
import signal
import sys
import threading
import time

PROJECT_ROOT = Path(__file__).resolve().parent
SRC_PATH = PROJECT_ROOT / "src"
if str(SRC_PATH) not in sys.path:
    sys.path.insert(0, str(SRC_PATH))

from logconsolidator.config.defaults import (  # noqa: E402
    POLL_INTERVAL_SECONDS,
    PROCESSED_QUEUE_MAXSIZE,
    QUEUE_GET_TIMEOUT_SECONDS,
    QUEUE_PUT_TIMEOUT_SECONDS,
    RAW_QUEUE_MAXSIZE,
    STATE_PATH,
)
from logconsolidator.config.loader import load_sources  # noqa: E402
from logconsolidator.core.logging import configure_logging  # noqa: E402
from logconsolidator.core.queues import PipelineQueues  # noqa: E402
from logconsolidator.ingest.state import PositionStateStore  # noqa: E402
from logconsolidator.ingest.watcher import FileWatcher  # noqa: E402
from logconsolidator.output.base import OutputAdapter  # noqa: E402
from logconsolidator.process.models import LogEntry, RawLogLine  # noqa: E402
from logconsolidator.process.normalizer import LogNormalizer  # noqa: E402
from logconsolidator.process.parser import RegexParserRouter  # noqa: E402


class TerminalAdapter(OutputAdapter):
    def handle(self, entry: LogEntry) -> None:
        payload = {
            "source_id": entry.source_id,
            "observed_at": entry.observed_at.isoformat(),
            "severity": entry.severity.value,
            "raw_message": entry.raw_message,
            **entry.fields,
        }
        print(json.dumps(payload))


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
        adapter: OutputAdapter,
        stop_event: threading.Event,
    ) -> None:
        super().__init__(name="dispatcher", daemon=True)
        self.processed_queue = processed_queue
        self.adapter = adapter
        self.stop_event = stop_event

    def run(self) -> None:
        while not self.stop_event.is_set():
            try:
                entry = self.processed_queue.get(timeout=QUEUE_GET_TIMEOUT_SECONDS)
            except queue.Empty:
                continue

            self.adapter.handle(entry)
            self.processed_queue.task_done()


def main() -> None:
    logger = configure_logging()
    stop_event = threading.Event()
    queues = PipelineQueues(
        raw_size=RAW_QUEUE_MAXSIZE,
        processed_size=PROCESSED_QUEUE_MAXSIZE,
    )
    state_store = PositionStateStore(STATE_PATH)

    sources = load_sources()
    for source in sources:
        inode = source.path.stat().st_ino if source.path.exists() else None
        state_store.update(source.source_id, inode=inode, offset=0)

    parser = RegexParserRouter(sources)
    normalizer = LogNormalizer()
    terminal_adapter = TerminalAdapter()

    watchers = [
        FileWatcher(
            source=source,
            raw_queue=queues.raw_queue,
            state_store=state_store,
            stop_event=stop_event,
            poll_interval=POLL_INTERVAL_SECONDS,
        )
        for source in sources
    ]

    processor = ProcessorWorker(
        raw_queue=queues.raw_queue,
        processed_queue=queues.processed_queue,
        parser=parser,
        normalizer=normalizer,
        stop_event=stop_event,
    )
    dispatcher = DispatcherWorker(
        processed_queue=queues.processed_queue,
        adapter=terminal_adapter,
        stop_event=stop_event,
    )

    def _handle_signal(_signum: int, _frame: object) -> None:
        stop_event.set()

    signal.signal(signal.SIGINT, _handle_signal)
    signal.signal(signal.SIGTERM, _handle_signal)

    for watcher in watchers:
        watcher.start()
    processor.start()
    dispatcher.start()
    logger.info("terminal test started: watchers=%d", len(watchers))

    while not stop_event.is_set():
        time.sleep(0.5)

    for watcher in watchers:
        watcher.join(timeout=2)
    processor.join(timeout=2)
    dispatcher.join(timeout=2)
    logger.info("terminal test stopped")


if __name__ == "__main__":
    main()
