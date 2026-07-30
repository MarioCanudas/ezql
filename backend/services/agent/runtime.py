from __future__ import annotations

from threading import RLock
from typing import Any

import httpx

from backend.services.agent.checkpoint import AgentCheckpointStore
from backend.services.agent.graph import create_agent_graph
from backend.services.agent.nodes.orchestrator import OrchestratorNode
from backend.services.agent.nodes.quality import QualityNode
from backend.services.agent.nodes.sql import SqlNode
from backend.services.agent.nodes.statistics import StatisticsNode
from backend.services.agent.nodes.statistics_grant import StatisticsGrantNode
from backend.services.agent.nodes.visualization import VisualizationNode

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


class AgentRuntime:
    """Worker-scoped immutable graph and reusable HTTP transport."""

    def __init__(self, checkpoint_store: AgentCheckpointStore) -> None:
        self.http_client = httpx.Client(
            limits=httpx.Limits(max_connections=32, max_keepalive_connections=16),
            timeout=httpx.Timeout(120.0, connect=10.0),
        )
        self.graph = create_agent_graph(
            OrchestratorNode(), SqlNode(), StatisticsNode(), StatisticsGrantNode(),
            VisualizationNode(), QualityNode(), checkpointer=checkpoint_store.saver,
        )

    def close(self) -> None:
        self.http_client.close()
