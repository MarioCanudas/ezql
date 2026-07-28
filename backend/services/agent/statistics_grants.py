from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from threading import Lock
from typing import Any
from uuid import uuid4

from backend.models.statistics import DatasetGrantDescriptor, StatisticsDatasetRequest
from backend.services.user_database import UserDatabase

GRANT_TTL_SECONDS = 300


@dataclass(frozen=True)
class _Grant:
    descriptor: DatasetGrantDescriptor
    user_id: int
    runtime_db_id: str
    expires_at: datetime
    records: list[dict[str, Any]]


class StatisticsGrantStore:
    """In-memory, short-lived data snapshots for a single agent execution.

    The graph stores only the descriptor; records are intentionally never added to
    LangGraph state, tool messages, logs, or metadata.
    """

    def __init__(self, *, ttl_seconds: int = GRANT_TTL_SECONDS) -> None:
        self._ttl = timedelta(seconds=ttl_seconds)
        self._grants: dict[str, _Grant] = {}
        self._lock = Lock()

    def create(
        self,
        *,
        database_service: UserDatabase,
        runtime_db_id: str,
        user_id: int,
        step_id: str,
        request: StatisticsDatasetRequest,
    ) -> DatasetGrantDescriptor:
        records, columns, truncated = database_service.materialize_statistics_dataset(
            runtime_db_id, user_id=user_id, request=request
        )
        grant_id = uuid4().hex
        warnings = ["El análisis se calculó sobre una muestra limitada."] if truncated else []
        descriptor = DatasetGrantDescriptor(
            grant_id=grant_id,
            step_id=step_id,
            mode=request.mode,
            columns=columns,
            row_count=len(records),
            truncated=truncated,
            warnings=warnings,
            # A descriptor may cross the durable graph boundary. Keep the
            # materialized rows exclusively in this execution-local store.
            sample=[],
        )
        grant = _Grant(
            descriptor=descriptor,
            user_id=user_id,
            runtime_db_id=runtime_db_id,
            expires_at=datetime.now(UTC) + self._ttl,
            records=records,
        )
        with self._lock:
            self._discard_expired_locked()
            self._grants[grant_id] = grant
        return descriptor

    def resolve(
        self, *, grant_id: str, step_id: str, user_id: int, runtime_db_id: str
    ) -> tuple[DatasetGrantDescriptor, list[dict[str, Any]]] | None:
        with self._lock:
            self._discard_expired_locked()
            grant = self._grants.get(grant_id)
            if grant is None or (
                grant.user_id != user_id
                or grant.runtime_db_id != runtime_db_id
                or grant.descriptor.step_id != step_id
            ):
                return None
            return grant.descriptor, grant.records.copy()

    def _discard_expired_locked(self) -> None:
        now = datetime.now(UTC)
        expired = [grant_id for grant_id, grant in self._grants.items() if grant.expires_at <= now]
        for grant_id in expired:
            self._grants.pop(grant_id, None)
