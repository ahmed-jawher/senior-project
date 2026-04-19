import re
from typing import Dict, Pattern

from logconsolidator.config.models import WatchSourceConfig
from logconsolidator.process.models import RawLogLine


class RegexParserRouter:
    """Keeps per-source compiled regex patterns and applies them to raw lines."""

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
            return self._classify(raw_line, {})

        extracted: Dict[str, str] = {}
        for field, pattern in patterns.items():
            match = pattern.search(raw_line.line)
            if match is None:
                continue
            extracted[field] = match.group(1) if match.groups() else match.group(0)

        return self._classify(raw_line, extracted)

    def _classify(self, raw_line: RawLogLine, fields: Dict[str, str]) -> Dict[str, str]:
        """
        Enrich parsed fields with normalized metadata for dashboards/analytics.
        We do NOT drop logs here. We only classify them.
        """
        line_lower = raw_line.line.lower()

        service = "unknown"
        event_type = "other"
        is_security_relevant = "false"

        # Detect service
        if "sshd" in line_lower:
            service = "sshd"
        elif "sudo" in line_lower:
            service = "sudo"

        # Classify SSH auth events
        if "sshd" in line_lower:
            if "failed password" in line_lower:
                event_type = "failed_login"
                is_security_relevant = "true"
                fields.setdefault("status", "Failed")
            elif "accepted password" in line_lower:
                event_type = "successful_login"
                is_security_relevant = "true"
                fields.setdefault("status", "Accepted")
            else:
                event_type = "ssh_event"
                is_security_relevant = "true"

        # Classify admin / investigation commands
        elif "sudo" in line_lower and "command=" in line_lower:
            event_type = "admin_command"
            is_security_relevant = "true"

            # Optional: extract command text if present
            command_marker = "command="
            idx = line_lower.find(command_marker)
            if idx != -1:
                fields.setdefault("command", raw_line.line[idx + len(command_marker):].strip())

        # Fallback
        else:
            event_type = "other"
            is_security_relevant = "false"

        fields["service"] = service
        fields["event_type"] = event_type
        fields["is_security_relevant"] = is_security_relevant

        return fields