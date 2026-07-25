from abc import ABC, abstractmethod
from typing import Any, ClassVar
from langchain_core.messages import BaseMessage, ToolMessage
from langchain_core.runnables import RunnableConfig
from langchain_core.messages import SystemMessage
from pydantic import ValidationError
from backend.models.blocks import MarkdownBlock
from backend.services.agent.state import (
    AgentConfiguration,
    AgentState,
    SpecialistContribution,
    SpecialistName,
)
from backend.services.agent.agent_chat import LLMGenerationError


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
    def __call__(self, state: AgentState, config: RunnableConfig) -> dict[str, Any]:
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

    def __call__(self, state: AgentState, config: RunnableConfig) -> dict[str, Any]:
        try:
            agent_config = AgentConfiguration.model_validate(config.get("configurable", {}))
        except ValidationError as exc:
            raise ValueError(f"Invalid configuration in config['configurable']: {exc}") from exc

        agent_config.database_service.get_database(
            agent_config.runtime_db_id, user_id=agent_config.user_id
        )
        if not state.pending_steps:
            return {}
        active_step = state.pending_steps[0]
        if active_step.specialist != self.step:
            return {}

        llm = agent_config.llm_service._build_client()
        messages = [
            SystemMessage(content=self.system_prompt),
            SystemMessage(
                content=(
                    "Objetivo de esta etapa: " + active_step.objective
                    + "\nUsa solo evidencia verificada por tus herramientas."
                )
            ),
        ] + sanitize_tool_calls_in_messages(list(state.messages))
        tool_names = {tool.name for tool in self.tools}
        has_tool_attempt = any(
            any(
                (call.get("name") if isinstance(call, dict) else getattr(call, "name", None))
                in tool_names
                for call in getattr(message, "tool_calls", [])
            )
            for message in state.messages
        )
        # No usamos ``tool_choice="required"``: algunos proveedores lo rechazan
        # para modelos con modo thinking. El segundo intento conserva el contrato
        # estándar de tools y únicamente refuerza la instrucción para el modelo.
        bound_llm = llm.bind_tools(self.tools, parallel_tool_calls=False)
        try:
            response = bound_llm.invoke(
                messages, config={"configurable": config.get("configurable", {})}
            )
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

        contribution_prompt = messages + [response, SystemMessage(content="""
Convierte los hallazgos verificados en piezas de presentación reutilizables.
Solo puedes proponer MarkdownBlock, MetricBlock, TableBlock o ChartBlock.
No crees tipos especializados para tendencias, anomalías o metodología.
Describe tendencias, anomalías, advertencias y recomendaciones en Markdown.
Nunca afirmes que EzQL no puede generar gráficas: una limitación solo se comunica
si una herramienta devolvió un fallo verificable para esta solicitud concreta.
Si incluyes una gráfica, copia exactamente el objeto `chart` de la evidencia
verificada. No inventes filas, métricas ni valores.
Si la herramienta de visualización devolvió un objeto `chart` válido, DEBES
incluir ese ChartBlock: la aplicación puede renderizarlo directamente.
""".strip())]
        artifact_ids = [artifact.tool_call_id for artifact in state.artifacts if artifact.ok]
        try:
            contribution = llm.with_structured_output(
                SpecialistContribution, method="json_schema"
            ).invoke(
                contribution_prompt,
                config={"configurable": config.get("configurable", {})},
            )
            contribution = SpecialistContribution.model_validate(contribution)
            contribution.step_id = active_step.id
            contribution.specialist = self.step
            contribution.artifact_ids = [
                artifact_id for artifact_id in contribution.artifact_ids if artifact_id in artifact_ids
            ]
        except Exception:
            narrative = str(response.content).strip() or "Análisis completado."
            contribution = SpecialistContribution(
                step_id=active_step.id,
                specialist=self.step,
                summary=narrative,
                artifact_ids=artifact_ids,
                blocks=[MarkdownBlock(content=narrative)],
            )

        return {
            "messages": [response],
            "pending_steps": state.pending_steps[1:],
            "completed_steps": [active_step],
            "contributions": [contribution],
        }
