from __future__ import annotations

from datetime import datetime, timezone
import queue
import signal
import sys
import threading
import time
from pathlib import Path
from types import FrameType

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
import logconsolidator.config as config  # noqa: E402
import logconsolidator.core as core  # noqa: E402
import logconsolidator.ingest as ingest  # noqa: E402
import logconsolidator.output as output  # noqa: E402
import logconsolidator.process as process  # noqa: E402


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
        while not self.stop_event.is_set():
            try:
                raw_line = self.raw_queue.get(timeout=QUEUE_GET_TIMEOUT_SECONDS)
            except queue.Empty:
                continue

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
    ) -> None:
        super().__init__(name="dispatcher", daemon=True)
        self.processed_queue = processed_queue
        self.adapters = adapters
        self.stop_event = stop_event

    def run(self) -> None:
        while not self.stop_event.is_set():
            try:
                entry = self.processed_queue.get(timeout=QUEUE_GET_TIMEOUT_SECONDS)
            except queue.Empty:
                continue

            for adapter in self.adapters:
                adapter.handle(entry)

            self.processed_queue.task_done()


def main() -> None:
    logger = core.configure_logging()
    stop_event = threading.Event()
    queues = core.PipelineQueues(
        raw_size=RAW_QUEUE_MAXSIZE,
        processed_size=PROCESSED_QUEUE_MAXSIZE,
    )
    state_store = ingest.PositionStateStore(STATE_PATH)

    sources = config.load_sources()
    parser = process.RegexParserRouter(sources)

    # Force a full replay by resetting every source cursor to the start of the file.
    for source in sources:
        inode = source.path.stat().st_ino if source.path.exists() else None
        state_store.update(source.source_id, inode=inode, offset=0)

    watchers = [
        ingest.FileWatcher(
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
        stop_event=stop_event,
    )
    adapters: list[output.OutputAdapter] = [output.StorageAdapter(), output.VectorAdapter()]
    dispatcher = DispatcherWorker(
        processed_queue=queues.processed_queue,
        adapters=adapters,
        stop_event=stop_event,
    )

    def _handle_signal(_signum: int, _frame: FrameType | None) -> None:
        stop_event.set()

    signal.signal(signal.SIGINT, _handle_signal)
    signal.signal(signal.SIGTERM, _handle_signal)

    for watcher in watchers:
        watcher.start()
    processor.start()
    dispatcher.start()
    logger.info("terminal test started: watchers=%d", len(watchers))

    try:
        while not stop_event.is_set():
            time.sleep(0.5)
    except KeyboardInterrupt:
        stop_event.set()
    finally:
        for watcher in watchers:
            watcher.join(timeout=2)
        processor.join(timeout=2)
        dispatcher.join(timeout=2)
        for adapter in adapters:
            adapter.close()
        logger.info("terminal test stopped")


if __name__ == "__main__":
    main()
