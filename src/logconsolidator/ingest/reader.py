from pathlib import Path

from logconsolidator.ingest.state import PositionStateStore


class LogReader:
    """Tail-like reader that returns only newly appended lines."""

    def __init__(self, source_id: str, path: Path, state_store: PositionStateStore) -> None:
        self.source_id = source_id
        self.path = path
        self.state_store = state_store
        saved = state_store.get(source_id)
        self._inode = saved.inode
        self._offset = saved.offset
        self._initialized = False

    def read_available_lines(self) -> list[str]:
        # -:- If source is temporarily unavailable, skip this cycle gracefully.
        if not self.path.exists():
            return []

        try:
            stat = self.path.stat()
        except OSError:
            return []

        # -:- On first loop, trust saved cursor only if inode/size still match.
        if not self._initialized:
            # -:- First boot starts at EOF when no trusted persisted position exists.
            if self._inode != stat.st_ino or self._offset > stat.st_size:
                self._offset = stat.st_size
            self._inode = stat.st_ino
            self._initialized = True
            self.state_store.update(self.source_id, self._inode, self._offset)
            return []

        # -:- Detect rotation/truncation and restart reading from beginning.
        if self._inode != stat.st_ino or stat.st_size < self._offset:
            self._inode = stat.st_ino
            self._offset = 0

        # -:- Read all lines appended since last known offset.
        lines: list[str] = []
        try:
            with self.path.open("r", encoding="utf-8", errors="replace") as handle:
                handle.seek(self._offset)
                for line in handle:
                    lines.append(line.rstrip("\n"))
                self._offset = handle.tell()
        except OSError:
            return []

        # -:- Persist new cursor after successful read.
        self.state_store.update(self.source_id, self._inode, self._offset)
        return lines
