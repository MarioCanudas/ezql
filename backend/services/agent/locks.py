from __future__ import annotations

from contextlib import contextmanager
import fcntl
import os
from pathlib import Path
from typing import Iterator


class ChatBusyError(RuntimeError):
    pass


class ChatExecutionLocks:
    """Cross-process, same-host serialization for a chat execution."""

    def __init__(self) -> None:
        self._directory = Path(os.getenv("EZQL_CHAT_LOCK_DIR", "/tmp/ezql-chat-locks"))
        self._directory.mkdir(parents=True, exist_ok=True)

    @contextmanager
    def acquire(self, chat_id: int) -> Iterator[None]:
        lock_path = self._directory / f"chat-{chat_id}.lock"
        handle = lock_path.open("a+")
        try:
            try:
                fcntl.flock(handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
            except BlockingIOError as exc:
                raise ChatBusyError("Este chat ya está procesando una consulta.") from exc
            yield
        finally:
            fcntl.flock(handle.fileno(), fcntl.LOCK_UN)
            handle.close()


chat_execution_locks = ChatExecutionLocks()
