from __future__ import annotations

import json
from typing import Any

from langchain_core.messages import ToolMessage
from langchain_core.runnables import RunnableConfig

from backend.services.agent.nodes.base import NodeBase
from backend.services.agent.metadata import build_artifact_metadata, presentation_catalog
from backend.services.agent.state import AgentConfiguration, AgentState, ToolArtifact


class ArtifactCollectorNode(NodeBase):
    """Promotes structured tool results into durable graph state exactly once."""

    def __call__(self, state: AgentState, config: RunnableConfig) -> dict[str, Any]:
        try:
            agent_config = AgentConfiguration.model_validate(config.get("configurable", {}))
        except Exception:
            agent_config = None
        get_value = state.get if isinstance(state, dict) else lambda key, default=None: getattr(state, key, default)
        known_ids = set(get_value("processed_tool_call_ids", []) or [])
        artifacts: list[ToolArtifact] = []
        processed: list[str] = []

        for message in get_value("messages", []) or []:
            if not isinstance(message, ToolMessage) or not message.tool_call_id:
                continue
            if message.tool_call_id in known_ids:
                continue
            processed.append(message.tool_call_id)
            try:
                payload: Any = json.loads(str(message.content))
            except (TypeError, json.JSONDecodeError):
                continue
            if not isinstance(payload, dict) or "ok" not in payload or "summary" not in payload:
                continue
            metadata, candidates = presentation_catalog(message.tool_call_id, payload.get("data"))
            if agent_config is not None and agent_config.artifact_store is not None:
                agent_config.artifact_store.put(message.tool_call_id, payload)
            artifacts.append(
                ToolArtifact(
                    tool_call_id=message.tool_call_id,
                    tool_name=getattr(message, "name", None),
                    ok=bool(payload["ok"]),
                    summary=str(payload["summary"]),
                    # Raw data remains in the execution-local store when the
                    # parent graph is checkpointed.
                    data=None if agent_config is not None and agent_config.artifact_store is not None else payload.get("data"),
                    warnings=list(payload.get("warnings", [])),
                    metadata=metadata,
                    debug_metadata=build_artifact_metadata(message.tool_call_id, payload.get("data")),
                    presentation_candidates=candidates,
                )
            )

        update: dict[str, Any] = {}
        if processed:
            update["processed_tool_call_ids"] = processed
        if artifacts:
            update["artifacts"] = artifacts
        return update
