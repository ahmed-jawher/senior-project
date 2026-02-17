from dataclasses import dataclass
from datetime import datetime
from enum import Enum
from typing import Dict


class Severity(str, Enum):
    INFO = "info"
    WARN = "warn"
    ERROR = "error"


@dataclass(frozen=True)
class RawLogLine:
    source_id: str
    line: str


@dataclass(frozen=True)
class LogEntry:
    source_id: str
    observed_at: datetime
    severity: Severity
    raw_message: str
    fields: Dict[str, str]
