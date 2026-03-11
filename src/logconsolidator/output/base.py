from abc import ABC, abstractmethod

from logconsolidator.process.models import LogEntry


class OutputAdapter(ABC):
    """Contract that every output sink must follow."""

    @abstractmethod
    def handle(self, entry: LogEntry) -> None:
        # -:- Consume one processed entry.
        raise NotImplementedError

    def close(self) -> None:
        # -:- Optional cleanup hook for adapters with open resources.
        return None
