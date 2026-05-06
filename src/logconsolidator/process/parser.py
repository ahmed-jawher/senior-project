from __future__ import annotations

import re
from typing import Pattern

from logconsolidator.config.models import ClassifyRule, WatchSourceConfig
from logconsolidator.process.models import RawLogLine

_DEFAULTS = {
    "service": "unknown",
    "event_type": "other",
    "severity": "low",
    "is_security_relevant": "false",
}


class RegexParserRouter:
    """Keeps per-source compiled regex patterns and applies them to raw lines."""

    def __init__(self, sources: list[WatchSourceConfig]) -> None:
        self._compiled: dict[str, dict[str, Pattern[str]]] = {}
        self._classify_rules: dict[str, list[ClassifyRule]] = {}
        self._extract_compiled: dict[str, list[dict[str, Pattern[str]]]] = {}
        for source in sources:
            self._compiled[source.source_id] = {
                field: re.compile(expr)
                for field, expr in source.parser.patterns.items()
            }
            self._classify_rules[source.source_id] = source.classify_rules
            self._extract_compiled[source.source_id] = [
                {name: re.compile(expr, re.IGNORECASE) for name, expr in rule.extract.items()}
                for rule in source.classify_rules
            ]

    def parse(self, raw_line: RawLogLine) -> dict[str, str]:
        patterns = self._compiled.get(raw_line.source_id, {})

        extracted: dict[str, str] = {}
        for field, pattern in patterns.items():
            match = pattern.search(raw_line.line)
            if match is None:
                continue
            value = _first_value(match)
            if value is not None:
                extracted[field] = value

        return self._classify(raw_line, extracted)

    def _classify(self, raw_line: RawLogLine, fields: dict[str, str]) -> dict[str, str]:
        line_lower = raw_line.line.lower()
        rules = self._classify_rules.get(raw_line.source_id, [])
        compiled_extracts = self._extract_compiled.get(raw_line.source_id, [])

        for rule, extracts in zip(rules, compiled_extracts):
            if rule.match.lower() not in line_lower:
                continue

            fields["service"] = rule.service
            fields["event_type"] = rule.event_type
            fields["severity"] = rule.severity
            fields["is_security_relevant"] = str(rule.is_security_relevant).lower()

            for field_name, pattern in extracts.items():
                m = pattern.search(raw_line.line)
                if m is None:
                    continue
                value = _first_value(m)
                if value is not None:
                    fields.setdefault(field_name, value)

            break

        for key, default in _DEFAULTS.items():
            fields.setdefault(key, default)
        return fields


def _first_value(match: re.Match[str]) -> str | None:
    """Return the first non-empty captured group, or the full match if no groups."""
    if match.groups():
        return next((g for g in match.groups() if g), None)
    return match.group(0)
