from pathlib import Path

# -:- Repository root inferred from this file's location.
PROJECT_ROOT = Path(__file__).resolve().parents[3]

# -:- Default input/output paths used across the application.
SOURCES_CONFIG_DIR = PROJECT_ROOT / "config" / "sources"
STATE_PATH = PROJECT_ROOT / "data" / "state" / "positions.json"
CHROMA_PATH = PROJECT_ROOT / "data" / "chroma"
CHROMA_COLLECTION = "logs"
REPORTS_DIR = PROJECT_ROOT / "data" / "reports"
STATIC_DIR = PROJECT_ROOT / "src" / "logconsolidator" / "static"

# -:- Queue capacities and worker polling/timeouts for pipeline threads.
RAW_QUEUE_MAXSIZE = 1000
PROCESSED_QUEUE_MAXSIZE = 1000
POLL_INTERVAL_SECONDS = 0.5
QUEUE_PUT_TIMEOUT_SECONDS = 0.5
QUEUE_GET_TIMEOUT_SECONDS = 0.5

# -:- OpenAI model defaults for the RAG layer.
OPENAI_CHAT_MODEL = "gpt-4o-mini"
OPENAI_REPORT_MODEL = "gpt-4o-mini"
RETRIEVER_DEFAULT_N_RESULTS = 10
