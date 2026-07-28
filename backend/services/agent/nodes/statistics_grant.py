from __future__ import annotations

import json
from typing import Any

from langchain_core.messages import HumanMessage, SystemMessage
from langchain_core.runnables import RunnableConfig
from pydantic import ValidationError

from backend.models.statistics import StatisticsDatasetRequest
from backend.services.agent.nodes.base import NodeBase
from backend.services.agent.state import AgentConfiguration, AgentState

STATISTICS_GRANT_PROMPT = """
Eres el orquestador de seguridad de EzQL. Autoriza el conjunto mínimo de datos
que necesita el especialista de estadística para su objetivo actual. Elige
`rows` para observaciones filtradas o `aggregates` para una tabla agrupada.
Solo usa tablas, columnas y valores presentes en la evidencia. Limita columnas
al mínimo necesario y no incluyas identificadores ni datos no relevantes.
No generes SQL. Tu salida debe seguir StatisticsDatasetRequest.
""".strip()


class StatisticsGrantNode(NodeBase):
    """Creates a bounded snapshot before the statistics specialist starts."""

    def __call__(self, state: AgentState, config: RunnableConfig) -> dict[str, Any]:
        get_value = state.get if isinstance(state, dict) else lambda key, default=None: getattr(state, key, default)
        active_task = get_value("task")
        if active_task is None:
            pending_steps = get_value("pending_steps", [])
            active_task = pending_steps[0] if pending_steps else None
        if active_task is None or active_task.specialist != "statistics":
            return {}
        if any(grant.step_id == active_task.id for grant in get_value("statistics_grants", [])):
            return {}
        try:
            agent_config = AgentConfiguration.model_validate(config.get("configurable", {}))
        except ValidationError as exc:
            raise ValueError(f"Invalid configuration in config['configurable']: {exc}") from exc

        evidence = []
        for artifact in get_value("artifacts", []):
            if not artifact.ok:
                continue
            payload = (
                agent_config.artifact_store.get(artifact.tool_call_id)
                if agent_config.artifact_store is not None
                else None
            )
            evidence.append({"tool": artifact.tool_name, "ok": artifact.ok, "data": payload.get("data") if payload else artifact.data})
        if not evidence:
            return {}
        try:
            request = agent_config.llm_service._build_client().with_structured_output(
                StatisticsDatasetRequest, method="json_schema"
            ).invoke(
                [
                    SystemMessage(content=STATISTICS_GRANT_PROMPT),
                    HumanMessage(content=json.dumps({
                        "objective": active_task.objective,
                        "evidence": evidence,
                    }, ensure_ascii=False, default=str)),
                ],
                config={"configurable": config.get("configurable", {})},
            )
            request = StatisticsDatasetRequest.model_validate(request)
            descriptor = agent_config.statistics_grants.create(
                database_service=agent_config.database_service,
                runtime_db_id=agent_config.runtime_db_id,
                user_id=agent_config.user_id,
                step_id=active_task.id,
                request=request,
            )
        except Exception:
            # A grant is additive. Conventional statistics tools remain usable.
            return {}
        return {"statistics_grants": [descriptor]}
