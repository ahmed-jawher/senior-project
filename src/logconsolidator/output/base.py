from abc import ABC, abstractmethod

from logconsolidator.process.models import LogEntry


class OutputAdapter(ABC):
    @abstractmethod
    def handle(self, entry: LogEntry) -> None:
        raise NotImplementedError

    def close(self) -> None:
        return None
