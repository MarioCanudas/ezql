from __future__ import annotations

import json
from typing import Any

from langchain_core.messages import ToolMessage
from langchain_core.runnables import RunnableConfig

from backend.services.agent.nodes.base import NodeBase
from backend.services.agent.state import AgentState, ToolArtifact


class ArtifactCollectorNode(NodeBase):
    """Promotes structured tool results into durable graph state exactly once."""

    def __call__(self, state: AgentState, config: RunnableConfig) -> dict[str, Any]:
        known_ids = set(state.processed_tool_call_ids)
        artifacts: list[ToolArtifact] = []
        processed: list[str] = []

        for message in state.messages:
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
            artifacts.append(
                ToolArtifact(
                    tool_call_id=message.tool_call_id,
                    tool_name=getattr(message, "name", None),
                    ok=bool(payload["ok"]),
                    summary=str(payload["summary"]),
                    data=payload.get("data"),
                    warnings=list(payload.get("warnings", [])),
                )
            )

        update: dict[str, Any] = {}
        if processed:
            update["processed_tool_call_ids"] = processed
        if artifacts:
            update["artifacts"] = artifacts
        return update
