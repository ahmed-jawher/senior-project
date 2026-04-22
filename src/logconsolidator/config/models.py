from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List


@dataclass(frozen=True)
class ClassifyRule:
    """One classification rule loaded from the source JSON."""

    match: str
    event_type: str
    severity: str
    is_security_relevant: bool
    service: str = "unknown"
    extract: Dict[str, str] = field(default_factory=dict)


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
    classify_rules: List[ClassifyRule] = field(default_factory=list)
