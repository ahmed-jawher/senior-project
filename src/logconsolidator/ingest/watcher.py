import queue
import threading
import time

from logconsolidator.config.defaults import QUEUE_PUT_TIMEOUT_SECONDS
from logconsolidator.config.models import WatchSourceConfig
from logconsolidator.ingest.reader import LogReader
from logconsolidator.ingest.state import PositionStateStore
from logconsolidator.process.models import RawLogLine


class FileWatcher(threading.Thread):
    def __init__(
        self,
        source: WatchSourceConfig,
        raw_queue: "queue.Queue[RawLogLine]",
        state_store: PositionStateStore,
        stop_event: threading.Event,
        poll_interval: float,
    ) -> None:
        super().__init__(name=f"watcher:{source.source_id}", daemon=True)
        self.source = source
        self.raw_queue = raw_queue
        self.state_store = state_store
        self.stop_event = stop_event
        self.poll_interval = poll_interval
        self.reader = LogReader(source.source_id, source.path, state_store)

    def run(self) -> None:
        while not self.stop_event.is_set():
            for line in self.reader.read_available_lines():
                payload = RawLogLine(source_id=self.source.source_id, line=line)
                self._put_with_backpressure(payload)
            time.sleep(self.poll_interval)

    def _put_with_backpressure(self, payload: RawLogLine) -> None:
        while not self.stop_event.is_set():
            try:
                self.raw_queue.put(payload, timeout=QUEUE_PUT_TIMEOUT_SECONDS)
                return
            except queue.Full:
                continue
