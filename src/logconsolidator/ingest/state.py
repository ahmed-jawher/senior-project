import json
import threading
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, Optional


@dataclass
class SourcePosition:
    inode: Optional[int]
    offset: int


class PositionStateStore:
    def __init__(self, state_path: Path) -> None:
        self.state_path = state_path
        self._lock = threading.Lock()
        self._state: Dict[str, SourcePosition] = {}
        self._load()

    def get(self, source_id: str) -> SourcePosition:
        with self._lock:
            return self._state.get(source_id, SourcePosition(inode=None, offset=0))

    def update(self, source_id: str, inode: Optional[int], offset: int) -> None:
        with self._lock:
            self._state[source_id] = SourcePosition(inode=inode, offset=offset)
            self._flush()

    def _load(self) -> None:
        if not self.state_path.exists():
            return
        try:
            raw = json.loads(self.state_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return

        if not isinstance(raw, dict):
            return

        for source_id, payload in raw.items():
            if not isinstance(payload, dict):
                continue
            inode = payload.get("inode")
            offset = payload.get("offset")
            if inode is not None and not isinstance(inode, int):
                inode = None
            if not isinstance(offset, int) or offset < 0:
                offset = 0
            self._state[source_id] = SourcePosition(inode=inode, offset=offset)

    def _flush(self) -> None:
        self.state_path.parent.mkdir(parents=True, exist_ok=True)
        serialized = {
            source_id: {"inode": pos.inode, "offset": pos.offset}
            for source_id, pos in self._state.items()
        }
        temp_path = self.state_path.with_suffix(".tmp")
        temp_path.write_text(json.dumps(serialized, indent=2), encoding="utf-8")
        temp_path.replace(self.state_path)
