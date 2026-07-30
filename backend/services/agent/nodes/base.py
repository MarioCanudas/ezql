from abc import ABC, abstractmethod
from typing import Any, ClassVar
from langchain_core.messages import BaseMessage, ToolMessage
from langchain_core.runnables import RunnableConfig
from langchain_core.messages import SystemMessage
from pydantic import ValidationError
from backend.models.blocks import MarkdownBlock
from backend.services.agent.state import (
    AgentConfiguration,
    SpecialistContribution,
    SpecialistName,
)
from backend.services.agent.agent_chat import LLMGenerationError
from backend.services.agent.metadata import sanitize_generated_block, state_metadata


def sanitize_tool_calls_in_messages(messages: list[BaseMessage]) -> list[BaseMessage]:
    """
    Ensures that every AIMessage with tool_calls is immediately followed by
    matching ToolMessages for all tool_call_ids. If any tool_call_id is missing
    a ToolMessage response, injects a fallback ToolMessage to satisfy API requirements.
    """
    sanitized: list[BaseMessage] = []
    n = len(messages)
    i = 0
    while i < n:
        msg = messages[i]
        sanitized.append(msg)
        i += 1

        tool_calls = getattr(msg, "tool_calls", None)
        if tool_calls:
            expected_ids = []
            for tc in tool_calls:
                tc_id = tc.get("id") if isinstance(tc, dict) else getattr(tc, "id", None)
                if tc_id:
                    expected_ids.append(tc_id)

            if expected_ids:
                existing_ids = set()
                while i < n and isinstance(messages[i], ToolMessage):
                    existing_ids.add(getattr(messages[i], "tool_call_id", None))
                    sanitized.append(messages[i])
                    i += 1

                for tid in expected_ids:
                    if tid not in existing_ids:
                        sanitized.append(
                            ToolMessage(content="Acción completada.", tool_call_id=tid)
                        )

    return sanitized


class NodeBase(ABC):
    @abstractmethod
    def __call__(self, state: Any, config: RunnableConfig) -> dict[str, Any]:
        """
        Execute the logic for this node in the Langgraph workflow.

        Args:
            state: The current state of the agent graph.
            config: The configuration which contains injected dependencies.

        Returns:
            A dictionary with updates to the agent state.
        """
        pass


class SpecialistNodeBase(NodeBase):
    """Shared execution loop for a tool-using specialist."""

    step: ClassVar[SpecialistName]
    system_prompt: ClassVar[str]
    tools: ClassVar[list]
    require_initial_tool_call: ClassVar[bool] = False

    def context_messages(self, state: Any, active_step: Any) -> list[SystemMessage]:
        return []

    def __call__(self, state: Any, config: RunnableConfig) -> dict[str, Any]:
        try:
            agent_config = AgentConfiguration.model_validate(config.get("configurable", {}))
        except ValidationError as exc:
            raise ValueError(f"Invalid configuration in config['configurable']: {exc}") from exc

        agent_config.database_service.get_database(
            agent_config.runtime_db_id, user_id=agent_config.user_id
        )
        get_value = state.get if isinstance(state, dict) else lambda key, default=None: getattr(state, key, default)
        active_task = get_value("task")
        if active_task is None:
            tasks = get_value("tasks", []) or []
            active_task = tasks[0] if tasks else None
        if active_task is None:
            return {}
        if active_task.specialist != self.step:
            return {}

        llm = agent_config.llm_service
        state_messages = get_value("messages", []) or []
        messages = [
            SystemMessage(content=self.system_prompt),
            SystemMessage(
                content=(
                    "Objetivo de esta etapa: " + active_task.objective
                    + "\nUsa solo evidencia verificada por tus herramientas."
                )
            ),
        ] + self.context_messages(state, active_task) + sanitize_tool_calls_in_messages(list(state_messages))
        tool_names = {tool.name for tool in self.tools}
        has_tool_attempt = any(
            any(
                (call.get("name") if isinstance(call, dict) else getattr(call, "name", None))
                in tool_names
                for call in getattr(message, "tool_calls", [])
            )
            for message in state_messages
        )
        # No usamos ``tool_choice="required"``: algunos proveedores lo rechazan
        # para modelos con modo thinking. El segundo intento conserva el contrato
        # estándar de tools y únicamente refuerza la instrucción para el modelo.
        # Tool calls inside a specialist stay serial unless a future specialist
        # explicitly opts into a safe, independent tool policy. Task-level
        # parallelism is handled by the parent graph with Send.
        bound_llm = llm.bind_tools(self.tools, parallel_tool_calls=False)
        try:
            response = bound_llm.invoke(messages, config={"configurable": config.get("configurable", {})})
            if (
                self.require_initial_tool_call
                and not has_tool_attempt
                and not getattr(response, "tool_calls", None)
            ):
                response = bound_llm.invoke(
                    messages
                    + [
                        SystemMessage(
                            content=(
                                "La solicitud requiere una gráfica. No respondas todavía: "
                                "elige y llama ahora una herramienta de visualización disponible."
                            )
                        )
                    ],
                    config={"configurable": config.get("configurable", {})},
                )
        except Exception as exc:
            raise LLMGenerationError(
                f"El especialista no pudo completar el análisis solicitado: {exc}"
            ) from exc

        if getattr(response, "tool_calls", None):
            return {"messages": [response]}

        state_artifacts = get_value("artifacts", []) or []
        available_metadata = state_metadata(state_artifacts)
        artifact_ids = [artifact.tool_call_id for artifact in state_artifacts if artifact.ok]
        narrative = str(response.content).strip() or "Análisis completado."
        contribution = SpecialistContribution(
            task_id=active_task.id,
            step_id=active_task.id,
            specialist=self.step,
            summary=narrative,
            artifact_ids=artifact_ids,
            blocks=[MarkdownBlock(content=narrative)],
        )

        contribution.blocks = [
            sanitize_generated_block(block, available_metadata)
            for block in contribution.blocks
            if block.type == "markdown"
        ]

        return {
            "messages": [response],
            "contributions": [contribution],
            "completed": True,
        }
