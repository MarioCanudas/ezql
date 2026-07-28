from __future__ import annotations

from contextlib import contextmanager
from threading import Lock
from typing import Iterator


class ChatExecutionLocks:
    """Process-local serialization for concurrent requests on one chat."""

    def __init__(self) -> None:
        self._registry_lock = Lock()
        self._locks: dict[int, Lock] = {}

    def _get(self, chat_id: int) -> Lock:
        with self._registry_lock:
            return self._locks.setdefault(chat_id, Lock())

    @contextmanager
    def acquire(self, chat_id: int) -> Iterator[None]:
        lock = self._get(chat_id)
        lock.acquire()
        try:
            yield
        finally:
            lock.release()


chat_execution_locks = ChatExecutionLocks()
