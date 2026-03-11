from dataclasses import dataclass
from datetime import datetime
from typing import Dict


@dataclass(frozen=True)
class RawLogLine:
    """Raw log payload produced by watcher threads."""

    source_id: str
    line: str


@dataclass(frozen=True)
class LogEntry:
    """Normalized event shared with all output adapters."""

    source_id: str
    observed_at: datetime
    raw_message: str
    fields: Dict[str, str]
