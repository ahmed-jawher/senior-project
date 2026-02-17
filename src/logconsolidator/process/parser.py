import re
from typing import Dict, Pattern

from logconsolidator.config.models import WatchSourceConfig
from logconsolidator.process.models import RawLogLine


class RegexParserRouter:
    def __init__(self, sources: list[WatchSourceConfig]) -> None:
        self._compiled: Dict[str, Dict[str, Pattern[str]]] = {}
        for source in sources:
            self._compiled[source.source_id] = {
                field: re.compile(expr)
                for field, expr in source.parser.patterns.items()
            }

    def parse(self, raw_line: RawLogLine) -> Dict[str, str]:
        patterns = self._compiled.get(raw_line.source_id)
        if patterns is None:
            return {}

        extracted: Dict[str, str] = {}
        for field, pattern in patterns.items():
            match = pattern.search(raw_line.line)
            if match is None:
                continue
            extracted[field] = match.group(1) if match.groups() else match.group(0)

        return extracted
