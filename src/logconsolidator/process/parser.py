import re
from typing import Dict, Pattern

from logconsolidator.config.models import WatchSourceConfig
from logconsolidator.process.models import RawLogLine


class RegexParserRouter:
    """Keeps per-source compiled regex patterns and applies them to raw lines."""

    def __init__(self, sources: list[WatchSourceConfig]) -> None:
        # -:- Compile once at startup instead of compiling on each log line.
        self._compiled: Dict[str, Dict[str, Pattern[str]]] = {}
        for source in sources:
            self._compiled[source.source_id] = {
                field: re.compile(expr)
                for field, expr in source.parser.patterns.items()
            }

    def parse(self, raw_line: RawLogLine) -> Dict[str, str]:
        # -:- Route the line to the parser config that belongs to its source id.
        patterns = self._compiled.get(raw_line.source_id)
        if patterns is None:
            return {}

        # -:- For each configured field, extract first match (group(1) or full match).
        extracted: Dict[str, str] = {}
        for field, pattern in patterns.items():
            match = pattern.search(raw_line.line)
            if match is None:
                continue
            extracted[field] = match.group(1) if match.groups() else match.group(0)

        return extracted
