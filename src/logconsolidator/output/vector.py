from __future__ import annotations

import hashlib
from pathlib import Path
from typing import Any, Callable

from logconsolidator.config.defaults import CHROMA_COLLECTION, CHROMA_PATH
from logconsolidator.output.base import OutputAdapter
from logconsolidator.process.models import LogEntry

try:
    import chromadb
except ImportError:  # pragma: no cover
    chromadb = None


class VectorAdapter(OutputAdapter):
    """Writes processed entries to a persistent ChromaDB collection."""

    def __init__(
        self,
        chroma_path: Path = CHROMA_PATH,
        collection_name: str = CHROMA_COLLECTION,
        client_factory: Callable[[str], Any] | None = None,
    ) -> None:
        self.chroma_path = chroma_path
        self.collection_name = collection_name
        self.chroma_path.mkdir(parents=True, exist_ok=True)

        if client_factory is None:
            if chromadb is None:
                raise RuntimeError("chromadb is not installed. Install it to enable VectorAdapter.")
            client_factory = chromadb.PersistentClient

        self._client = client_factory(str(self.chroma_path))
        self._collection = self._client.get_or_create_collection(name=self.collection_name)

    def handle(self, entry: LogEntry) -> None:
        document = self._build_document(entry)
        metadata = self._build_metadata(entry)
        entry_id = self._build_id(entry)
        self._collection.upsert(
            ids=[entry_id],
            documents=[document],
            metadatas=[metadata],
        )

    def _build_document(self, entry: LogEntry) -> str:
        lines = [f"source: {entry.source_id}"]
        for field, value in sorted(entry.fields.items()):
            lines.append(f"{field}: {value}")
        lines.append(f"message: {entry.raw_message}")
        return "\n".join(lines)

    def _build_metadata(self, entry: LogEntry) -> dict[str, str]:
        metadata = {
            "source_id": entry.source_id,
            "observed_at": entry.observed_at.isoformat(),
        }
        metadata.update({field: str(value) for field, value in sorted(entry.fields.items())})
        return metadata

    def _build_id(self, entry: LogEntry) -> str:
        raw = "|".join(
            [entry.source_id, entry.observed_at.isoformat(), entry.raw_message]
        ).encode("utf-8")
        return hashlib.sha256(raw).hexdigest()
