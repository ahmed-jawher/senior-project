import json
import os
import re
from pathlib import Path
from typing import Any, Dict, List

from logconsolidator.config.defaults import SOURCES_CONFIG_DIR
from logconsolidator.config.models import ParserConfig, WatchSourceConfig
from logconsolidator.core.exceptions import ConfigError


def load_sources(config_dir: Path = SOURCES_CONFIG_DIR) -> List[WatchSourceConfig]:
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

    parsed_sources: List[WatchSourceConfig] = []
    for config_path in config_paths:
        payload = _load_json(config_path)
        parsed_sources.append(_parse_source(payload, config_path))

    ids = [src.source_id for src in parsed_sources]
    if len(ids) != len(set(ids)):
        raise ConfigError("Each source id must be unique")

    return parsed_sources


def _load_json(path: Path) -> Dict[str, Any]:
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


def _parse_source(raw: Dict[str, Any], config_path: Path) -> WatchSourceConfig:
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
    typed_patterns: Dict[str, str] = {}
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

    return WatchSourceConfig(
        source_id=source_id,
        path=path,
        parser=ParserConfig(parser_type="regex", patterns=typed_patterns),
    )
