import json
from typing import Any

from langchain_core.messages import AIMessage, HumanMessage, SystemMessage
from langchain_core.runnables import RunnableConfig
from pydantic import ValidationError

from backend.models.blocks import AgentResponse, MarkdownBlock
from backend.prompts.orchestrator import (
    ORCHESTRATOR_FORMATTER_PROMPT,
    ORCHESTRATOR_PLANNER_PROMPT,
)
from backend.services.agent.agent_chat import LLMGenerationError
from backend.services.agent.nodes.base import NodeBase, sanitize_tool_calls_in_messages
from backend.services.agent.state import AgentConfiguration, AgentState, ExecutionPlan


def _last_specialist_text(messages: list[Any]) -> str:
    for message in reversed(messages):
        if isinstance(message, AIMessage) and message.content and not message.tool_calls:
            return str(message.content).strip()
    return ""


def _blocks_from_artifacts(state: AgentState) -> list[dict[str, Any]]:
    blocks: list[dict[str, Any]] = []
    for artifact in state.artifacts:
        if artifact.ok:
            blocks.extend(artifact.blocks)
    return blocks


class OrchestratorNode(NodeBase):
    """Plans once, advances specialists, and formats exactly one final response."""

    def __call__(self, state: AgentState, config: RunnableConfig) -> dict[str, Any]:
        try:
            agent_config = AgentConfiguration.model_validate(config.get("configurable", {}))
        except ValidationError as exc:
            raise ValueError(f"Invalid configuration in config['configurable']: {exc}") from exc

        agent_config.database_service.get_database(
            agent_config.runtime_db_id, user_id=agent_config.user_id
        )
        llm = agent_config.llm_service._build_client()
        messages = sanitize_tool_calls_in_messages(list(state.messages))

        if not state.plan_created:
            plan_messages = [SystemMessage(content=ORCHESTRATOR_PLANNER_PROMPT)] + messages
            try:
                plan = llm.with_structured_output(ExecutionPlan, method="json_schema").invoke(
                    plan_messages,
                    config={"configurable": config.get("configurable", {})},
                )
            except Exception:
                # A data analyst should prefer a safe SQL discovery pass if the provider
                # cannot produce structured planning output.
                plan = ExecutionPlan(steps=["sql"])
            return {"plan": plan.steps, "plan_created": True}

        if len(state.completed_steps) < len(state.plan):
            return {}

        artifact_data = [artifact.model_dump() for artifact in state.artifacts]
        formatter_messages = [SystemMessage(content=ORCHESTRATOR_FORMATTER_PROMPT)] + messages
        if artifact_data:
            formatter_messages.append(
                HumanMessage(
                    content="[RESULTADOS_VERIFICADOS]\n"
                    + json.dumps(artifact_data, ensure_ascii=False, default=str)
                )
            )

        try:
            response = llm.with_structured_output(AgentResponse, method="json_schema").invoke(
                formatter_messages,
                config={"configurable": config.get("configurable", {})},
            )
        except Exception:
            try:
                response = llm.with_structured_output(AgentResponse, method="json_mode").invoke(
                    formatter_messages,
                    config={"configurable": config.get("configurable", {})},
                )
            except Exception as exc:
                raise LLMGenerationError("No se pudo preparar una respuesta para el usuario.") from exc

        blocks = _blocks_from_artifacts(state)
        if blocks:
            narrative = _last_specialist_text(messages)
            response.blocks = ([MarkdownBlock(content=narrative)] if narrative else []) + blocks
        elif not response.blocks:
            response.blocks = [MarkdownBlock(content=response.summary)]

        validated = AgentResponse.model_validate(response)
        return {
            "response": validated.model_dump(),
            "messages": [AIMessage(content=validated.summary)],
        }
