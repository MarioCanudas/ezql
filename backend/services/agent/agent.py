from __future__ import annotations

from collections.abc import Sequence
from langchain_core.messages import HumanMessage, SystemMessage

from backend.models import AgentReply, Messages, AgentResponse, MarkdownBlock
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
from backend.services.agent.nodes.statistics_grant import StatisticsGrantNode
from backend.services.agent.nodes.quality import QualityNode
from backend.services.agent.statistics_grants import StatisticsGrantStore
from backend.services.agent.checkpoint import AgentCheckpointStore, get_checkpoint_store
from backend.services.agent.runtime import ExecutionArtifactStore


class AnalystAgent:
    def __init__(
        self,
        *,
        database_service: UserDatabase,
        model_name: str,
        provider: str | None,
        api_key: str,
        temperature: float = 0.0,
        reasoning_effort: str | None = None,
        checkpoint_store: AgentCheckpointStore | None = None,
    ) -> None:
        if not api_key or not api_key.strip():
            raise LLMConfigurationError("The API key is required and cannot be empty.")

        self.database_service = database_service
        self.llm_service = AgentChat(
            model_name=model_name,
            provider=provider,
            api_key=api_key,
            temperature=temperature,
            reasoning_effort=reasoning_effort,
        )

        self.orchestrator_node = OrchestratorNode()
        self.sql_node = SqlNode()
        self.statistics_node = StatisticsNode()
        self.statistics_grant_node = StatisticsGrantNode()
        self.visualization_node = VisualizationNode()
        self.quality_node = QualityNode()
        self.statistics_grants = StatisticsGrantStore()
        self.checkpoint_store = checkpoint_store or get_checkpoint_store()

        self.graph = create_agent_graph(
            self.orchestrator_node,
            self.sql_node,
            self.statistics_node,
            self.statistics_grant_node,
            self.visualization_node,
            self.quality_node,
            checkpointer=self.checkpoint_store.saver,
        )

    def generate_reply(
        self,
        *,
        user_message: str,
        history: Sequence[Messages],
        summary: str | None,
        runtime_db_id: str,
        user_id: int,
        thread_id: str | None = None,
        recursion_limit: int = 150,
    ) -> AgentReply:
        message = user_message.strip()
        if not message:
            return AgentReply(
                text="Escribe una pregunta sobre tu base de datos.",
                blocks=[MarkdownBlock(content="Escribe una pregunta sobre tu base de datos.")],
            )

        chat_messages = []
        if summary:
            chat_messages.append(SystemMessage(content=f"Resumen del chat: {summary}"))
        history_msgs = self.llm_service._history_messages(history)
        chat_messages.extend(history_msgs)
        if not history_msgs or not (
            isinstance(history_msgs[-1], HumanMessage) and history_msgs[-1].content == message
        ):
            chat_messages.append(HumanMessage(content=message))

        initial_state = AgentState()
        artifact_store = ExecutionArtifactStore()

        config_dict = {
            "database_service": self.database_service,
            "llm_service": self.llm_service,
            "runtime_db_id": runtime_db_id,
            "user_id": user_id,
            "statistics_grants": self.statistics_grants,
            "artifact_store": artifact_store,
            "input_messages": chat_messages,
            "thread_id": thread_id,
        }
        graph_config = {
            "configurable": {
                **config_dict,
                "thread_id": thread_id or f"ephemeral-{user_id}-{id(initial_state)}",
            },
            "recursion_limit": recursion_limit,
        }

        try:
            try:
                response = self.graph.invoke(initial_state, config=graph_config)
            except Exception:
                # LangGraph persists the last successful super-step. Reusing the
                # same thread lets us retry only the failed branch.
                if not thread_id:
                    raise
                graph_config["configurable"]["retry_attempt"] = 2
                response = self.graph.invoke(None, config=graph_config)
            text_response = str(response.get("response", {}).get("summary", ""))
        except (LLMGenerationError, RuntimeDatabaseError):
            raise
        except Exception as exc:
            import logging
            logging.getLogger(__name__).exception("AnalystAgent graph execution failed: %s", exc)
            raise LLMGenerationError(
                f"Error al generar la respuesta del asistente: {exc}"
            ) from exc

        parsed_response = self._extract_agent_response(response, text_response)

        return AgentReply(
            text=parsed_response.summary,
            response=parsed_response,
            blocks=parsed_response.blocks,
            data=artifact_store.values(),
            metadata=parsed_response.metadata,
        )

    def _extract_agent_response(
        self, graph_output: dict, fallback_text: str
    ) -> AgentResponse:
        """Reads the final validated response from graph state."""
        response = graph_output.get("response")
        if isinstance(response, dict):
            try:
                return AgentResponse.model_validate(response)
            except Exception:
                pass
        return AgentResponse(
            summary=fallback_text,
            blocks=[MarkdownBlock(content=fallback_text)],
        )
