from __future__ import annotations

from collections.abc import Sequence
from langchain_core.messages import HumanMessage, SystemMessage

from backend.models import AgentReply, Messages
from backend.services.agent.agent_chat import (
    AgentChat,
    LLMGenerationError,
    LLMConfigurationError,
)
from backend.services.user_database import UserDatabase, RuntimeDatabaseError
from backend.services.agent.graph import create_agent_graph
from backend.services.agent.state import AgentState
from backend.services.agent.nodes.orchestrator import OrchestratorNode
from backend.services.agent.nodes.sql import SqlNode
from backend.services.agent.nodes.statistics import StatisticsNode
from backend.services.agent.nodes.visualization import VisualizationNode


class AnalystAgent:
    def __init__(
        self,
        *,
        database_service: UserDatabase,
        model_name: str,
        provider: str | None,
        api_key: str,
        temperature: float = 0.0,
    ) -> None:
        if not api_key or not api_key.strip():
            raise LLMConfigurationError("The API key is required and cannot be empty.")

        self.database_service = database_service
        self.llm_service = AgentChat(
            model_name=model_name,
            provider=provider,
            api_key=api_key,
            temperature=temperature,
        )

        self.orchestrator_node = OrchestratorNode()
        self.sql_node = SqlNode()
        self.statistics_node = StatisticsNode()
        self.visualization_node = VisualizationNode()

        self.graph = create_agent_graph(
            self.orchestrator_node,
            self.sql_node,
            self.statistics_node,
            self.visualization_node,
        )

    def generate_reply(
        self,
        *,
        user_message: str,
        history: Sequence[Messages],
        summary: str | None,
        runtime_db_id: str,
        user_id: int,
    ) -> AgentReply:
        message = user_message.strip()
        if not message:
            return AgentReply(text="Escribe una pregunta sobre tu base de datos.")

        chat_messages = []
        if summary:
            chat_messages.append(SystemMessage(content=f"Resumen del chat: {summary}"))
        history_msgs = self.llm_service._history_messages(history)
        chat_messages.extend(history_msgs)
        if not history_msgs or not (
            isinstance(history_msgs[-1], HumanMessage) and history_msgs[-1].content == message
        ):
            chat_messages.append(HumanMessage(content=message))

        initial_state = AgentState(messages=chat_messages)

        from backend.services.agent.state import AgentConfiguration
        agent_config = AgentConfiguration(
            database_service=self.database_service,
            llm_service=self.llm_service,
            runtime_db_id=runtime_db_id,
            user_id=user_id,
        )

        query_data_ref = []
        config_dict = agent_config.model_dump()
        config_dict["query_data_ref"] = query_data_ref

        DEFAULT_RECURSION_LIMIT = 50

        try:
            response = self.graph.invoke(
                initial_state,
                config={
                    "configurable": config_dict,
                    "recursion_limit": DEFAULT_RECURSION_LIMIT,
                },
            )
            text_response = str(response["messages"][-1].content)
        except (LLMGenerationError, RuntimeDatabaseError):
            raise
        except Exception as exc:
            import logging
            logging.getLogger(__name__).exception("AnalystAgent graph execution failed: %s", exc)
            raise LLMGenerationError(
                f"Error al generar la respuesta del asistente: {exc}"
            ) from exc

        return AgentReply(text=text_response, data=query_data_ref)
