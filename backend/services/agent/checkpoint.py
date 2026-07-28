from __future__ import annotations

import os
import sqlite3
from pathlib import Path
from threading import RLock
from langgraph.checkpoint.sqlite import SqliteSaver


class AgentCheckpointStore:
    """Shared local SQLite checkpointer for parent graph state."""

    def __init__(self, path: str | Path | None = None) -> None:
        configured_path = path or os.getenv(
            "EZQL_AGENT_CHECKPOINT_DB", "backend/agent_checkpoints.db"
        )
        self.path = Path(configured_path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.connection = sqlite3.connect(str(self.path), check_same_thread=False)
        self.connection.execute("PRAGMA journal_mode=WAL")
        self.connection.execute("PRAGMA busy_timeout=5000")
        self.saver = SqliteSaver(self.connection)
        self.saver.setup()
        self._lock = RLock()

    def delete_thread(self, thread_id: str) -> None:
        with self._lock:
            self.saver.delete_thread(thread_id)

    def delete_threads(self, thread_ids: list[str]) -> None:
        with self._lock:
            for thread_id in thread_ids:
                self.saver.delete_thread(thread_id)

    def close(self) -> None:
        with self._lock:
            self.connection.close()


_checkpoint_store: AgentCheckpointStore | None = None


def get_checkpoint_store() -> AgentCheckpointStore:
    global _checkpoint_store
    if _checkpoint_store is None:
        _checkpoint_store = AgentCheckpointStore()
    return _checkpoint_store


def close_checkpoint_store() -> None:
    global _checkpoint_store
    if _checkpoint_store is not None:
        _checkpoint_store.close()
        _checkpoint_store = None
