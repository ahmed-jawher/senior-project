#!/usr/bin/env python3
"""One-shot launcher: starts the ingest pipeline + FastAPI server in a single process.

Usage:
    python3 main.py                # start everything
    python3 main.py --port 9000    # custom API port
    python3 main.py --no-api       # pipeline only (no HTTP server)

Ctrl+C cleanly stops both.
"""
from __future__ import annotations

import argparse
import logging
import signal
import sys
import threading
from pathlib import Path
from types import FrameType

# Make `import logconsolidator...` work without a `pip install -e .` first.
_SRC = Path(__file__).resolve().parent / "src"
if str(_SRC) not in sys.path:
    sys.path.insert(0, str(_SRC))

from logconsolidator.core.exceptions import ConfigError  # noqa: E402
from logconsolidator.main import LogConsolidatorApp  # noqa: E402

logger = logging.getLogger("logconsolidator.launcher")


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Start logconsolidator (pipeline + API)")
    parser.add_argument("--host", default="0.0.0.0", help="API bind host (default: 0.0.0.0)")
    parser.add_argument("--port", type=int, default=8000, help="API bind port (default: 8000)")
    parser.add_argument("--no-api", action="store_true", help="Run only the ingest pipeline")
    return parser.parse_args()


def main() -> int:
    args = _parse_args()

    pipeline = LogConsolidatorApp()
    try:
        pipeline.start()
    except ConfigError as exc:
        pipeline.logger.error("configuration error: %s", exc)
        return 1

    api_thread: threading.Thread | None = None
    server = None
    if not args.no_api:
        try:
            import uvicorn
            from logconsolidator.api.server import create_app
        except ImportError as exc:
            pipeline.logger.error("API dependencies missing (%s); start with --no-api or install them", exc)
            pipeline.stop()
            return 1

        config = uvicorn.Config(
            create_app(),
            host=args.host,
            port=args.port,
            log_level="info",
        )
        server = uvicorn.Server(config)
        # Uvicorn installs its own SIGINT handler by default — disable so our
        # handler below can stop both pipeline and server together.
        server.install_signal_handlers = lambda: None
        api_thread = threading.Thread(target=server.run, name="api-server", daemon=True)
        api_thread.start()
        pipeline.logger.info("api listening on http://%s:%d", args.host, args.port)

    def _shutdown(_signum: int, _frame: FrameType | None) -> None:
        pipeline.stop_event.set()
        if server is not None:
            server.should_exit = True

    signal.signal(signal.SIGINT, _shutdown)
    signal.signal(signal.SIGTERM, _shutdown)

    try:
        pipeline.stop_event.wait()
    finally:
        if server is not None:
            server.should_exit = True
        if api_thread is not None:
            api_thread.join(timeout=5)
        pipeline.stop()

    return 0


if __name__ == "__main__":
    sys.exit(main())
