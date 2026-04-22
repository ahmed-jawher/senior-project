import re
from typing import Dict, List, Pattern

from logconsolidator.config.models import ClassifyRule, WatchSourceConfig
from logconsolidator.process.models import RawLogLine


class RegexParserRouter:
    """Keeps per-source compiled regex patterns and applies them to raw lines."""

    def __init__(self, sources: List[WatchSourceConfig]) -> None:
        self._compiled: Dict[str, Dict[str, Pattern[str]]] = {}
        self._classify_rules: Dict[str, List[ClassifyRule]] = {}
        for source in sources:
            self._compiled[source.source_id] = {
                field: re.compile(expr)
                for field, expr in source.parser.patterns.items()
            }
            self._classify_rules[source.source_id] = source.classify_rules

    def parse(self, raw_line: RawLogLine) -> Dict[str, str]:
        patterns = self._compiled.get(raw_line.source_id, {})

        extracted: Dict[str, str] = {}
        for field, pattern in patterns.items():
            match = pattern.search(raw_line.line)
            if match is None:
                continue
            if match.groups():
                value = next((g for g in match.groups() if g), None)
                if value is not None:
                    extracted[field] = value
            else:
                extracted[field] = match.group(0)

        return self._classify(raw_line, extracted)

    def _classify(self, raw_line: RawLogLine, fields: Dict[str, str]) -> Dict[str, str]:
        line_lower = raw_line.line.lower()
        rules = self._classify_rules.get(raw_line.source_id, [])

        for rule in rules:
            if rule.match.lower() not in line_lower:
                continue

            fields["service"] = rule.service
            fields["event_type"] = rule.event_type
            fields["severity"] = rule.severity
            fields["is_security_relevant"] = str(rule.is_security_relevant).lower()

            for field_name, pattern in rule.extract.items():
                m = re.search(pattern, raw_line.line, re.IGNORECASE)
                if m:
                    value = next((g for g in m.groups() if g), None) if m.groups() else m.group(0)
                    if value is not None:
                        fields.setdefault(field_name, value)

            return fields

        fields.setdefault("service", "unknown")
        fields.setdefault("event_type", "other")
        fields.setdefault("severity", "low")
        fields.setdefault("is_security_relevant", "false")
        return fields
