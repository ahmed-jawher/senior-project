from dataclasses import dataclass
from typing import Dict
from datetime import datetime


@dataclass(frozen=True)
class RawLogLine:
    """Raw log payload produced by watcher threads."""

    source_id: str
    line: str


@dataclass(frozen=True)
class LogEntry:
    """Normalized event shared with all output adapters."""

    source_id: str
    timestamp: str
    raw_message: str
    fields: Dict[str, str]
