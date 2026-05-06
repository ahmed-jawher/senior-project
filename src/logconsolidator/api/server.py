from __future__ import annotations

from contextlib import asynccontextmanager
from datetime import date as _date
import json
import logging
import os

try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:  # pragma: no cover
    pass

try:
    from fastapi import FastAPI, HTTPException, Request
    from fastapi.responses import FileResponse, StreamingResponse
    from fastapi.staticfiles import StaticFiles
    from pydantic import BaseModel
except ImportError:  # pragma: no cover
    FastAPI = None

from logconsolidator.config.defaults import REPORTS_DIR, STATIC_DIR
from logconsolidator.query.rag import RAGEngine
from logconsolidator.query.report_fetcher import ReportFetcher
from logconsolidator.query.retriever import LogRetriever
from logconsolidator.query.scheduler import ReportScheduler

logger = logging.getLogger(__name__)


def _parse_iso_date(value: str) -> _date:
    """Parse YYYY-MM-DD strictly; raise HTTPException 400 on any malformed input."""
    try:
        return _date.fromisoformat(value)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=f"date must be YYYY-MM-DD: {exc}") from exc


if FastAPI is not None:

    class QueryRequest(BaseModel):
        question: str


@asynccontextmanager
async def _lifespan(app):
    # -:- Retriever and fetcher don't need the OpenAI key; construct them best-effort.
    app.state.retriever = None
    app.state.fetcher = ReportFetcher()
    app.state.engine = None
    app.state.scheduler = None

    try:
        app.state.retriever = LogRetriever()
    except Exception:
        logger.exception("failed to initialize LogRetriever")

    if os.environ.get("OPENAI_API_KEY") and not os.environ["OPENAI_API_KEY"].startswith("sk-your-key"):
        try:
            app.state.engine = RAGEngine()
            app.state.scheduler = ReportScheduler(app.state.engine, app.state.fetcher)
            app.state.scheduler.start()
        except Exception:
            logger.exception("failed to start RAG engine / scheduler")
    else:
        logger.warning("OPENAI_API_KEY not set (or placeholder); /query and the report scheduler are disabled")

    try:
        yield
    finally:
        scheduler = app.state.scheduler
        if scheduler is not None:
            scheduler.request_stop()
            scheduler.join(timeout=5)


def create_app():
    if FastAPI is None:
        raise RuntimeError("FastAPI is not installed. Install it to enable the API server.")

    REPORTS_DIR.mkdir(parents=True, exist_ok=True)
    STATIC_DIR.mkdir(parents=True, exist_ok=True)

    app = FastAPI(title="logconsolidator", lifespan=_lifespan)

    @app.get("/health")
    def health() -> dict[str, str]:
        return {"status": "ok"}

    @app.post("/query")
    def query(req: QueryRequest, request: Request):
        question = req.question.strip()
        if not question:
            raise HTTPException(status_code=400, detail="question is required")

        engine = request.app.state.engine
        retriever = request.app.state.retriever
        if engine is None or retriever is None:
            raise HTTPException(
                status_code=503,
                detail="RAG engine unavailable. Set OPENAI_API_KEY and restart.",
            )

        def event_stream():
            try:
                for token in engine.stream_answer(question, retriever):
                    yield f"data: {json.dumps(token)}\n\n"
            except Exception as exc:  # pragma: no cover
                logger.exception("stream_answer failed")
                yield f"data: {json.dumps({'error': str(exc)})}\n\n"
            finally:
                yield "data: [DONE]\n\n"

        return StreamingResponse(event_stream(), media_type="text/event-stream")

    @app.get("/reports")
    def list_reports() -> dict[str, list[str]]:
        if not REPORTS_DIR.exists():
            return {"dates": []}
        valid_dates: list[str] = []
        for path in REPORTS_DIR.glob("*.md"):
            try:
                _date.fromisoformat(path.stem)
            except ValueError:
                continue
            valid_dates.append(path.stem)
        return {"dates": sorted(valid_dates, reverse=True)}

    @app.post("/reports/{date}/generate")
    def trigger_report(date: str, request: Request):
        target = _parse_iso_date(date)
        engine = request.app.state.engine
        fetcher = request.app.state.fetcher
        if engine is None:
            raise HTTPException(status_code=503, detail="RAG engine unavailable.")
        engine.generate_report(fetcher, target)
        return {"status": "ok", "date": date}

    @app.get("/reports/{date}")
    def get_report(date: str):
        _parse_iso_date(date)
        path = REPORTS_DIR / f"{date}.md"
        if not path.exists():
            raise HTTPException(status_code=404, detail=f"no report for {date}")
        return FileResponse(path, media_type="text/markdown")

    app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")

    @app.get("/")
    def index():
        index_path = STATIC_DIR / "index.html"
        if not index_path.exists():
            raise HTTPException(status_code=404, detail="index.html not found")
        return FileResponse(index_path, media_type="text/html")

    return app
