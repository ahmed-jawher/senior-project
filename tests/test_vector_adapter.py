from __future__ import annotations

from pathlib import Path
import tempfile
import unittest

from logconsolidator.output.vector import VectorAdapter
from logconsolidator.process.models import LogEntry


class FakeCollection:
    def __init__(self, store: dict[str, dict[str, object]]) -> None:
        self.store = store

    def upsert(
        self,
        *,
        ids: list[str],
        documents: list[str],
        metadatas: list[dict[str, str]],
    ) -> None:
        for entry_id, document, metadata in zip(ids, documents, metadatas):
            self.store[entry_id] = {
                "document": document,
                "metadata": metadata,
            }


class FakeClient:
    _databases: dict[tuple[str, str], dict[str, dict[str, object]]] = {}

    def __init__(self, path: str) -> None:
        self.path = path

    def get_or_create_collection(self, name: str) -> FakeCollection:
        key = (self.path, name)
        store = self._databases.setdefault(key, {})
        return FakeCollection(store)


class VectorAdapterTests(unittest.TestCase):
    def setUp(self) -> None:
        FakeClient._databases.clear()
        self.temp_dir = tempfile.TemporaryDirectory()
        self.chroma_path = Path(self.temp_dir.name) / "chroma"
        self.entry = LogEntry(
            source_id="auth",
            timestamp="Mar 14 10:20:00",
            raw_message="Failed password for invalid user admin from 192.168.1.10 port 22 ssh2",
            fields={"user": "admin", "ip": "192.168.1.10"},
        )

    def tearDown(self) -> None:
        self.temp_dir.cleanup()

    def test_init_creates_chroma_directory(self) -> None:
        VectorAdapter(chroma_path=self.chroma_path, client_factory=FakeClient)
        self.assertTrue(self.chroma_path.exists())
        self.assertTrue(self.chroma_path.is_dir())

    def test_handle_stores_composite_document_and_metadata(self) -> None:
        adapter = VectorAdapter(chroma_path=self.chroma_path, client_factory=FakeClient)

        adapter.handle(self.entry)

        store = FakeClient._databases[(str(self.chroma_path), "logs")]
        self.assertEqual(len(store), 1)
        payload = next(iter(store.values()))
        self.assertEqual(
            payload["document"],
            "\n".join(
                [
                    "source: auth",
                    "ip: 192.168.1.10",
                    "user: admin",
                    "message: Failed password for invalid user admin from 192.168.1.10 port 22 ssh2",
                ]
            ),
        )
        self.assertEqual(
            payload["metadata"],
            {
                "source_id": "auth",
                "timestamp": "Mar 14 10:20:00",
                "ip": "192.168.1.10",
                "user": "admin",
            },
        )

    def test_document_excludes_timestamp(self) -> None:
        adapter = VectorAdapter(chroma_path=self.chroma_path, client_factory=FakeClient)

        adapter.handle(self.entry)

        store = FakeClient._databases[(str(self.chroma_path), "logs")]
        document = next(iter(store.values()))["document"]
        self.assertNotIn("timestamp", document)
        self.assertNotIn("Mar 14 10:20:00", document)

    def test_upsert_keeps_duplicate_entry_singleton(self) -> None:
        adapter = VectorAdapter(chroma_path=self.chroma_path, client_factory=FakeClient)

        adapter.handle(self.entry)
        adapter.handle(self.entry)

        store = FakeClient._databases[(str(self.chroma_path), "logs")]
        self.assertEqual(len(store), 1)

    def test_storage_persists_across_adapter_instances_for_same_path(self) -> None:
        first_adapter = VectorAdapter(chroma_path=self.chroma_path, client_factory=FakeClient)
        first_adapter.handle(self.entry)

        second_adapter = VectorAdapter(chroma_path=self.chroma_path, client_factory=FakeClient)

        store = FakeClient._databases[(str(self.chroma_path), "logs")]
        self.assertEqual(len(store), 1)
        self.assertIsNotNone(second_adapter)


if __name__ == "__main__":
    unittest.main()
