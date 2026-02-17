from dataclasses import dataclass
from pathlib import Path
from typing import Dict


@dataclass(frozen=True)
class ParserConfig:
    parser_type: str
    patterns: Dict[str, str]


@dataclass(frozen=True)
class WatchSourceConfig:
    source_id: str
    path: Path
    parser: ParserConfig
