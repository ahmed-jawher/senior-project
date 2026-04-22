from __future__ import annotations

import json
from typing import Any, Dict, Iterable, List


def build_chat_system_prompt() -> str:
    return (
        "You are a log analyst assistant for a log consolidation system. "
        "You answer the user's question using ONLY the log entries provided in the context. "
        "If the context does not contain the information needed, say so plainly instead of guessing. "
        "Cite specific timestamps, source ids, and field values when they support your answer. "
        "Prefer concise, structured answers; use bullet points or short tables for multiple events."
    )


def build_chat_context(results: List[Dict[str, Any]]) -> str:
    if not results:
        return "No matching log entries were found in the vector store."

    rendered: List[str] = []
    for index, result in enumerate(results, start=1):
        metadata = result.get("metadata") or {}
        document = (result.get("document") or "").strip()
        source = metadata.get("source_id", "unknown")
        observed_at = metadata.get("observed_at", "unknown-time")
        rendered.append(
            f"[{index}] source={source} observed_at={observed_at}\n{document}"
        )
    return "\n\n".join(rendered)


def build_report_system_prompt() -> str:
    return (
        "You are a log analyst writing a daily operations report. "
        "Summarize the provided 24-hour log slice into a structured markdown report. "
        "Use exactly these section headings (and nothing else at the top level): "
        "'## Summary', '## Notable Events', '## Top Sources', '## Anomalies / Warnings'. "
        "Cite concrete counts, source ids, and example timestamps. "
        "Call out any events where is_security_relevant=true or severity=high. "
        "If a section has no relevant content, write 'None observed.' under it. "
        "Do not invent data that is not present in the provided logs."
    )


def build_report_context(rows: Iterable[Dict[str, Any]]) -> str:
    rendered: List[str] = []
    total = 0
    for row in rows:
        total += 1
        observed_at = row.get("observed_at")
        timestamp = observed_at.isoformat() if hasattr(observed_at, "isoformat") else str(observed_at)
        source = row.get("source_id", "unknown")
        raw_message = (row.get("raw_message") or "").strip()
        fields = _extract_fields(row.get("fields_json"))
        field_summary = ", ".join(f"{key}={value}" for key, value in sorted(fields.items())) if fields else "-"
        rendered.append(f"{timestamp} [{source}] {field_summary} :: {raw_message}")

    if total == 0:
        return "No log entries were recorded in this window."

    header = f"Total entries in window: {total}"
    return header + "\n\n" + "\n".join(rendered)


def _extract_fields(fields_json: Any) -> Dict[str, str]:
    # -:- fields_json is the full serialized payload; filter to the parsed fields only.
    if not fields_json:
        return {}
    if isinstance(fields_json, dict):
        data = fields_json
    elif isinstance(fields_json, str):
        try:
            data = json.loads(fields_json)
        except json.JSONDecodeError:
            return {}
    else:
        return {}
    if not isinstance(data, dict):
        return {}
    reserved = {"source_id", "observed_at", "raw_message"}
    return {
        key: str(value)
        for key, value in data.items()
        if key not in reserved and value is not None
    }
