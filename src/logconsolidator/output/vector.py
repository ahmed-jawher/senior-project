from logconsolidator.output.base import OutputAdapter
from logconsolidator.process.models import LogEntry


class VectorAdapter(OutputAdapter):
    """Placeholder sink. Replace with ChromaDB integration later."""

    def handle(self, entry: LogEntry) -> None:
        _ = entry
