from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[3]

SOURCES_CONFIG_DIR = PROJECT_ROOT / "config" / "sources"
STATE_PATH = PROJECT_ROOT / "data" / "state" / "positions.json"
PROCESSED_OUTPUT_PATH = PROJECT_ROOT / "data" / "processed.jsonl"

RAW_QUEUE_MAXSIZE = 1000
PROCESSED_QUEUE_MAXSIZE = 1000
POLL_INTERVAL_SECONDS = 0.5
QUEUE_PUT_TIMEOUT_SECONDS = 0.5
QUEUE_GET_TIMEOUT_SECONDS = 0.5
