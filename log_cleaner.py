import json
import os
import re
import sys
from typing import Dict, List, Optional, Tuple


def load_config_paths(config_dir: str) -> List[str]:
    """Return a list of JSON config file paths in the configs directory."""
    if not os.path.isdir(config_dir):
        return []
    return [
        os.path.join(config_dir, name)
        for name in os.listdir(config_dir)
        if name.endswith(".json")
    ]


def read_json_file(path: str) -> Optional[dict]:
    """Load and parse a JSON file, returning None on failure."""
    try:
        with open(path, "r", encoding="utf-8") as handle:
            return json.load(handle)
    except (OSError, json.JSONDecodeError) as exc:
        print(f"config error: failed to read {path}: {exc}", file=sys.stderr)
        return None


def resolve_log_path(config_path: str, log_path: str) -> str:
    """Resolve a log path that can be absolute or relative."""
    if os.path.isabs(log_path):
        return log_path
    config_dir = os.path.dirname(config_path)
    return os.path.normpath(os.path.join(config_dir, log_path))


def compile_patterns(patterns: Dict[str, str], config_path: str) -> Optional[Dict[str, re.Pattern]]:
    """Compile regex patterns once; return None if any are invalid."""
    compiled: Dict[str, re.Pattern] = {}
    for field, pattern in patterns.items():
        try:
            compiled[field] = re.compile(pattern)
        except re.error as exc:
            print(
                f"config error: invalid regex in {config_path} for field '{field}': {exc}",
                file=sys.stderr,
            )
            return None
    return compiled


def validate_config(config: dict, config_path: str) -> Optional[Tuple[str, str, Dict[str, re.Pattern]]]:
    """Validate required config fields and return parsed values."""
    log_name = config.get("log_name")
    log_path = config.get("path")
    parser = config.get("parser", {})

    if not isinstance(log_name, str) or not log_name:
        print(f"config error: missing log_name in {config_path}", file=sys.stderr)
        return None

    if not isinstance(log_path, str) or not log_path:
        print(f"config error: missing path in {config_path}", file=sys.stderr)
        return None

    if parser.get("type") != "regex":
        print(f"config error: unsupported parser type in {config_path}", file=sys.stderr)
        return None

    patterns = parser.get("patterns")
    if not isinstance(patterns, dict) or not patterns:
        print(f"config error: missing patterns in {config_path}", file=sys.stderr)
        return None

    compiled = compile_patterns(patterns, config_path)
    if compiled is None:
        return None

    resolved_path = resolve_log_path(config_path, log_path)
    return log_name, resolved_path, compiled


def process_log(log_name: str, log_path: str, patterns: Dict[str, re.Pattern]) -> None:
    """Read a log file line by line and print structured JSON for matches."""
    if not os.path.isfile(log_path) or not os.access(log_path, os.R_OK):
        print(f"log error: cannot read {log_path}", file=sys.stderr)
        return

    try:
        with open(log_path, "r", encoding="utf-8", errors="replace") as handle:
            for line in handle:
                line = line.rstrip("\n")
                extracted: Dict[str, str] = {}

                # Apply each regex independently and collect any matches.
                for field, pattern in patterns.items():
                    match = pattern.search(line)
                    if match:
                        # Fall back to group 0 if the pattern lacks a capturing group.
                        extracted[field] = match.group(1) if match.groups() else match.group(0)

                if extracted:
                    record = {"log_name": log_name, **extracted, "raw_message": line}
                    print(json.dumps(record))
    except OSError as exc:
        print(f"log error: failed to read {log_path}: {exc}", file=sys.stderr)


def run() -> None:
    """Load configs and process each log source."""
    config_dir = os.path.join(os.path.dirname(__file__), "configs")
    config_paths = load_config_paths(config_dir)

    if not config_paths:
        print("config error: no config files found", file=sys.stderr)
        return

    for config_path in config_paths:
        config = read_json_file(config_path)
        if config is None:
            continue

        validated = validate_config(config, config_path)
        if validated is None:
            continue

        log_name, log_path, patterns = validated
        process_log(log_name, log_path, patterns)
