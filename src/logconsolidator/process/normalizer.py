from datetime import datetime, timezone
from typing import Dict

from logconsolidator.process.models import LogEntry, RawLogLine, Severity


class LogNormalizer:
    def normalize(self, raw_line: RawLogLine, fields: Dict[str, str]) -> LogEntry:
        severity = self._derive_severity(fields)
        return LogEntry(
            source_id=raw_line.source_id,
            observed_at=datetime.now(timezone.utc),
            severity=severity,
            raw_message=raw_line.line,
            fields=fields,
        )

    def _derive_severity(self, fields: Dict[str, str]) -> Severity:
        status = fields.get("status", "").lower()
        if "fail" in status:
            return Severity.ERROR
        if "warn" in status:
            return Severity.WARN
        return Severity.INFO
