from dataclasses import dataclass
from pathlib import Path
from typing import Dict


@dataclass(frozen=True)
class ParserConfig:
    """Parser definition attached to one source."""

    parser_type: str
    patterns: Dict[str, str]


@dataclass(frozen=True)
class WatchSourceConfig:
    """Validated configuration for one watched log file."""

    source_id: str
    path: Path
    parser: ParserConfig
