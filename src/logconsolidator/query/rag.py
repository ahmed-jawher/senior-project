from __future__ import annotations

from datetime import date as date_type
import logging
from pathlib import Path
from typing import Any, Callable, Iterator, Optional

from logconsolidator.config.defaults import (
    OPENAI_CHAT_MODEL,
    OPENAI_REPORT_MODEL,
    REPORTS_DIR,
)
from logconsolidator.query.context import (
    build_chat_context,
    build_chat_system_prompt,
    build_report_context,
    build_report_system_prompt,
)
from logconsolidator.query.report_fetcher import ReportFetcher
from logconsolidator.query.retriever import LogRetriever

try:
    from openai import OpenAI
except ImportError:  # pragma: no cover
    OpenAI = None

logger = logging.getLogger(__name__)


class RAGEngine:
    """Wraps the OpenAI client for chat streaming and report generation."""

    def __init__(
        self,
        reports_dir: Path = REPORTS_DIR,
        chat_model: str = OPENAI_CHAT_MODEL,
        report_model: str = OPENAI_REPORT_MODEL,
        client_factory: Optional[Callable[[], Any]] = None,
    ) -> None:
        self.reports_dir = reports_dir
        self.chat_model = chat_model
        self.report_model = report_model
        self.reports_dir.mkdir(parents=True, exist_ok=True)

        if client_factory is None:
            if OpenAI is None:
                raise RuntimeError("openai is not installed. Install it to enable RAGEngine.")
            client_factory = OpenAI
        self._client = client_factory()

    def stream_answer(self, question: str, retriever: LogRetriever) -> Iterator[str]:
        results = retriever.query(question)
        context = build_chat_context(results)
        system_prompt = build_chat_system_prompt()
        user_message = (
            f"Question:\n{question}\n\n"
            f"Retrieved log context:\n{context}"
        )

        stream = self._client.chat.completions.create(
            model=self.chat_model,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_message},
            ],
            stream=True,
        )
        for chunk in stream:
            choices = getattr(chunk, "choices", None)
            if not choices:
                continue
            delta = getattr(choices[0], "delta", None)
            if delta is None:
                continue
            content = getattr(delta, "content", None)
            if content:
                yield content

    def generate_report(self, fetcher: ReportFetcher, target_date: date_type) -> str:
        rows = fetcher.fetch_last_24h(target_date)
        context = build_report_context(rows)
        system_prompt = build_report_system_prompt()
        user_message = (
            f"Report date (UTC): {target_date.isoformat()}\n\n"
            f"Log entries for this window:\n{context}"
        )

        response = self._client.chat.completions.create(
            model=self.report_model,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_message},
            ],
        )
        body = response.choices[0].message.content or ""
        report = f"# Log Report — {target_date.isoformat()}\n\n{body.strip()}\n"
        self._write_report(target_date, report)
        return report

    def _write_report(self, target_date: date_type, content: str) -> None:
        report_path = self.reports_dir / f"{target_date.isoformat()}.md"
        report_path.write_text(content, encoding="utf-8")
        logger.info("wrote report: %s", report_path)
