from __future__ import annotations

from pathlib import Path
from typing import Any, Callable, Dict, List

from logconsolidator.config.defaults import (
    CHROMA_COLLECTION,
    CHROMA_PATH,
    RETRIEVER_DEFAULT_N_RESULTS,
)

try:
    import chromadb
except ImportError:  # pragma: no cover
    chromadb = None


class LogRetriever:
    """Semantic search over the ChromaDB collection populated by VectorAdapter."""

    def __init__(
        self,
        chroma_path: Path = CHROMA_PATH,
        collection_name: str = CHROMA_COLLECTION,
        client_factory: Callable[[str], Any] | None = None,
    ) -> None:
        if client_factory is None:
            if chromadb is None:
                raise RuntimeError("chromadb is not installed. Install it to enable LogRetriever.")
            client_factory = chromadb.PersistentClient

        chroma_path.mkdir(parents=True, exist_ok=True)
        self._client = client_factory(str(chroma_path))
        self._collection = self._client.get_or_create_collection(name=collection_name)

    def query(
        self,
        question: str,
        n_results: int = RETRIEVER_DEFAULT_N_RESULTS,
    ) -> List[Dict[str, Any]]:
        # -:- Empty collection is valid — return early before the vector query runs.
        available = self._collection.count()
        if available == 0:
            return []

        raw = self._collection.query(
            query_texts=[question],
            n_results=min(n_results, available),
        )

        documents = (raw.get("documents") or [[]])[0]
        metadatas = (raw.get("metadatas") or [[]])[0]
        distances = (raw.get("distances") or [[]])[0]

        results: List[Dict[str, Any]] = []
        for index, document in enumerate(documents):
            results.append(
                {
                    "document": document,
                    "metadata": metadatas[index] if index < len(metadatas) else {},
                    "distance": distances[index] if index < len(distances) else None,
                }
            )
        return results
