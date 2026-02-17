from pathlib import Path

from logconsolidator.ingest.state import PositionStateStore


class LogReader:
    def __init__(self, source_id: str, path: Path, state_store: PositionStateStore) -> None:
        self.source_id = source_id
        self.path = path
        self.state_store = state_store
        saved = state_store.get(source_id)
        self._inode = saved.inode
        self._offset = saved.offset
        self._initialized = False

    def read_available_lines(self) -> list[str]:
        if not self.path.exists():
            return []

        try:
            stat = self.path.stat()
        except OSError:
            return []

        if not self._initialized:
            # First boot starts at EOF when no trusted persisted position exists.
            if self._inode != stat.st_ino or self._offset > stat.st_size:
                self._offset = stat.st_size
            self._inode = stat.st_ino
            self._initialized = True
            self.state_store.update(self.source_id, self._inode, self._offset)
            return []

        if self._inode != stat.st_ino or stat.st_size < self._offset:
            self._inode = stat.st_ino
            self._offset = 0

        lines: list[str] = []
        try:
            with self.path.open("r", encoding="utf-8", errors="replace") as handle:
                handle.seek(self._offset)
                for line in handle:
                    lines.append(line.rstrip("\n"))
                self._offset = handle.tell()
        except OSError:
            return []

        self.state_store.update(self.source_id, self._inode, self._offset)
        return lines
