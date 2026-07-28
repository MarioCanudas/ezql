from __future__ import annotations

from threading import RLock
from typing import Any


class ExecutionArtifactStore:
    """Execution-local raw payload store.

    The parent graph receives only safe artifact references. Raw tool payloads
    live here for the duration of one request and are never sent to the durable
    LangGraph checkpointer.
    """

    def __init__(self) -> None:
        self._lock = RLock()
        self._payloads: dict[str, dict[str, Any]] = {}

    def put(self, artifact_id: str, payload: dict[str, Any]) -> None:
        with self._lock:
            self._payloads[artifact_id] = payload

    def get(self, artifact_id: str) -> dict[str, Any] | None:
        with self._lock:
            payload = self._payloads.get(artifact_id)
            return dict(payload) if payload is not None else None

    def values(self) -> list[dict[str, Any]]:
        with self._lock:
            return [dict(payload) for payload in self._payloads.values()]

    def clear(self) -> None:
        with self._lock:
            self._payloads.clear()
