from dataclasses import dataclass
from datetime import datetime
from typing import Dict

@dataclass(frozen=True)
class RawLogLine:
    source_id: str
    line: str


@dataclass(frozen=True)
class LogEntry:
    source_id: str
    observed_at: datetime
    raw_message: str
    fields: Dict[str, str]
