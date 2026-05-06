from __future__ import annotations

import json
import os
import re
from pathlib import Path
from typing import Any

from logconsolidator.config.defaults import SOURCES_CONFIG_DIR
from logconsolidator.config.models import ClassifyRule, ParserConfig, WatchSourceConfig
from logconsolidator.core.exceptions import ConfigError

_VALID_SEVERITIES = ("low", "medium", "high")


def load_sources(config_dir: Path = SOURCES_CONFIG_DIR) -> list[WatchSourceConfig]:
    """Load all source JSON files, validate them, and return typed configs."""
    # -:- Fail fast when the source directory itself is missing or misconfigured.
    if not config_dir.exists():
        raise ConfigError(f"Missing config directory: {config_dir}")
    if not config_dir.is_dir():
        raise ConfigError(f"Expected directory for sources config: {config_dir}")

    # -:- Every JSON file under config/sources represents one watch source.
    config_paths = sorted(path for path in config_dir.glob("*.json") if path.is_file())
    if not config_paths:
        raise ConfigError("config/sources must contain at least one .json source file")

    parsed_sources: list[WatchSourceConfig] = []
    for config_path in config_paths:
        payload = _load_json(config_path)
        parsed_sources.append(_parse_source(payload, config_path))

    ids = [src.source_id for src in parsed_sources]
    if len(ids) != len(set(ids)):
        raise ConfigError("Each source id must be unique")

    return parsed_sources


def _load_json(path: Path) -> dict[str, Any]:
    """Read one JSON source file and ensure the top-level object shape."""
    try:
        with path.open("r", encoding="utf-8") as handle:
            data = json.load(handle)
    except OSError as exc:
        raise ConfigError(f"Failed to read {path}: {exc}") from exc
    except json.JSONDecodeError as exc:
        raise ConfigError(f"Invalid JSON in {path}: {exc}") from exc

    if not isinstance(data, dict):
        raise ConfigError("Top-level config must be a JSON object")

    return data


def _parse_source(raw: dict[str, Any], config_path: Path) -> WatchSourceConfig:
    """Validate one source record and convert it into WatchSourceConfig."""
    # -:- Read required fields from the JSON payload.
    source_id = raw.get("id")
    path_raw = raw.get("path")
    parser_raw = raw.get("parser")

    if not isinstance(source_id, str) or not source_id.strip():
        raise ConfigError("Each source requires a non-empty string 'id'")

    if not isinstance(path_raw, str) or not path_raw.strip():
        raise ConfigError(f"Source '{source_id}' requires a non-empty string 'path'")

    if not isinstance(parser_raw, dict):
        raise ConfigError(f"Source '{source_id}' requires object 'parser'")

    parser_type = parser_raw.get("type")
    if parser_type != "regex":
        raise ConfigError(f"Source '{source_id}' supports only parser.type='regex'")

    patterns = parser_raw.get("patterns")
    if not isinstance(patterns, dict) or not patterns:
        raise ConfigError(f"Source '{source_id}' requires non-empty parser.patterns")

    # -:- Compile-check regex expressions during startup to catch bad config early.
    typed_patterns: dict[str, str] = {}
    for field, expression in patterns.items():
        if not isinstance(field, str) or not isinstance(expression, str):
            raise ConfigError(f"Source '{source_id}' has non-string parser pattern")
        try:
            re.compile(expression)
        except re.error as exc:
            raise ConfigError(
                f"Source '{source_id}' has invalid regex for '{field}': {exc}"
            ) from exc
        typed_patterns[field] = expression

    # -:- Resolve relative file paths from the config file location.
    path = Path(path_raw)
    if not path.is_absolute():
        path = (config_path.parent / path).resolve()

    # -:- Verify the input log file exists and is readable before starting workers.
    if not path.exists():
        raise ConfigError(f"Source '{source_id}' path does not exist: {path}")
    if not path.is_file():
        raise ConfigError(f"Source '{source_id}' path is not a file: {path}")
    if not os.access(path, os.R_OK):
        raise ConfigError(f"Source '{source_id}' path is not readable: {path}")

    classify_rules = _parse_classify_rules(raw, source_id)

    return WatchSourceConfig(
        source_id=source_id,
        path=path,
        parser=ParserConfig(parser_type="regex", patterns=typed_patterns),
        classify_rules=classify_rules,
    )


def _parse_classify_rules(raw: dict[str, Any], source_id: str) -> list[ClassifyRule]:
    classify_raw = raw.get("classify", [])
    if not isinstance(classify_raw, list):
        raise ConfigError(f"Source '{source_id}' classify must be an array")

    rules: list[ClassifyRule] = []
    for i, rule in enumerate(classify_raw):
        if not isinstance(rule, dict):
            raise ConfigError(f"Source '{source_id}' classify[{i}] must be an object")

        match = rule.get("match")
        if not isinstance(match, str) or not match:
            raise ConfigError(f"Source '{source_id}' classify[{i}] requires non-empty string 'match'")

        event_type = rule.get("event_type")
        if not isinstance(event_type, str) or not event_type:
            raise ConfigError(f"Source '{source_id}' classify[{i}] requires non-empty string 'event_type'")

        severity = rule.get("severity", "low")
        if severity not in _VALID_SEVERITIES:
            raise ConfigError(
                f"Source '{source_id}' classify[{i}] severity must be one of {_VALID_SEVERITIES}"
            )

        is_security_relevant = rule.get("is_security_relevant", False)
        if not isinstance(is_security_relevant, bool):
            raise ConfigError(f"Source '{source_id}' classify[{i}] is_security_relevant must be boolean")

        service = rule.get("service", "unknown")
        if not isinstance(service, str) or not service:
            raise ConfigError(f"Source '{source_id}' classify[{i}] service must be a non-empty string")

        extract = rule.get("extract", {})
        if not isinstance(extract, dict):
            raise ConfigError(f"Source '{source_id}' classify[{i}] extract must be an object")
        for field_name, expr in extract.items():
            if not isinstance(field_name, str) or not isinstance(expr, str):
                raise ConfigError(
                    f"Source '{source_id}' classify[{i}] extract.{field_name} must be string→string"
                )
            try:
                re.compile(expr)
            except re.error as exc:
                raise ConfigError(
                    f"Source '{source_id}' classify[{i}] extract.{field_name} invalid regex: {exc}"
                ) from exc

        rules.append(ClassifyRule(
            match=match,
            event_type=event_type,
            severity=severity,
            is_security_relevant=is_security_relevant,
            service=service,
            extract=extract,
        ))

    return rules
