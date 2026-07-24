from typing import Any
from langchain_core.messages import SystemMessage
from langchain_core.runnables import RunnableConfig
from pydantic import ValidationError

from backend.services.agent.state import AgentState, AgentConfiguration
from backend.services.agent.nodes.base import NodeBase, sanitize_tool_calls_in_messages
from backend.services.agent.tools import visualization_tools
from backend.prompts.visualization import VISUALIZATION_SYSTEM_PROMPT
from backend.services.agent.agent_chat import LLMGenerationError


class VisualizationNode(NodeBase):
    def __call__(self, state: AgentState, config: RunnableConfig) -> dict[str, Any]:
        """
        Visualization Node that creates charts and graphs using Altair.
        """
        try:
            agent_config = AgentConfiguration.model_validate(config.get("configurable", {}))
        except ValidationError as e:
            raise ValueError(f"Invalid configuration in config['configurable']: {e}")

        # Check if database exists early (Fail Fast)
        agent_config.database_service.get_database(
            agent_config.runtime_db_id, user_id=agent_config.user_id
        )

        llm = agent_config.llm_service._build_client()
        llm_with_tools = llm.bind_tools(visualization_tools, parallel_tool_calls=False)

        sanitized_messages = sanitize_tool_calls_in_messages(list(state.messages))
        messages = [SystemMessage(content=VISUALIZATION_SYSTEM_PROMPT)] + sanitized_messages

        try:
            response = llm_with_tools.invoke(
                messages,
                config={"configurable": config.get("configurable", {})},
            )
            return {"messages": [response]}
        except Exception as exc:
            import logging
            logging.getLogger(__name__).exception("VisualizationNode execution failed: %s", exc)
            raise LLMGenerationError(
                f"El asistente de visualización no pudo generar una respuesta: {exc}"
            ) from exc
