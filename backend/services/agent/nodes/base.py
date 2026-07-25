from abc import ABC, abstractmethod
from typing import Any, ClassVar
from langchain_core.messages import BaseMessage, ToolMessage
from langchain_core.runnables import RunnableConfig
from langchain_core.messages import SystemMessage
from pydantic import ValidationError
from backend.services.agent.state import AgentState
from backend.services.agent.state import AgentConfiguration, SpecialistName
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

    def __call__(self, state: AgentState, config: RunnableConfig) -> dict[str, Any]:
        try:
            agent_config = AgentConfiguration.model_validate(config.get("configurable", {}))
        except ValidationError as exc:
            raise ValueError(f"Invalid configuration in config['configurable']: {exc}") from exc

        agent_config.database_service.get_database(
            agent_config.runtime_db_id, user_id=agent_config.user_id
        )
        llm = agent_config.llm_service._build_client()
        messages = [SystemMessage(content=self.system_prompt)] + sanitize_tool_calls_in_messages(
            list(state.messages)
        )
        try:
            response = llm.bind_tools(self.tools, parallel_tool_calls=False).invoke(
                messages, config={"configurable": config.get("configurable", {})}
            )
        except Exception as exc:
            raise LLMGenerationError(
                f"El especialista no pudo completar el análisis solicitado: {exc}"
            ) from exc

        update: dict[str, Any] = {"messages": [response]}
        if not getattr(response, "tool_calls", None) and self.step not in state.completed_steps:
            update["completed_steps"] = [self.step]
        return update
