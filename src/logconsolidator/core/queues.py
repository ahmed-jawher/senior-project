import queue

from logconsolidator.process.models import LogEntry, RawLogLine


class PipelineQueues:
    def __init__(self, raw_size: int, processed_size: int) -> None:
        self.raw_queue: "queue.Queue[RawLogLine]" = queue.Queue(maxsize=raw_size)
        self.processed_queue: "queue.Queue[LogEntry]" = queue.Queue(maxsize=processed_size)
