from typing import Any
from langchain_core.runnables import RunnableConfig
from pydantic import ValidationError
from langchain_core.messages import SystemMessage

from backend.services.agent.state import AgentState, AgentConfiguration
from backend.services.agent.nodes.base import NodeBase, sanitize_tool_calls_in_messages
from backend.prompts import SQL_AGENT_SYSTEM_PROMPT
from backend.services.agent.agent_chat import LLMGenerationError
from backend.services.agent.tools import sql_tools


class SqlNode(NodeBase):
    def __call__(self, state: AgentState, config: RunnableConfig) -> dict[str, Any]:
        """
        SQL Node that invokes the LLM bound to tools.
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
        llm_with_tools = llm.bind_tools(sql_tools, parallel_tool_calls=False)

        sanitized_messages = sanitize_tool_calls_in_messages(list(state.messages))
        messages = [SystemMessage(content=SQL_AGENT_SYSTEM_PROMPT)] + sanitized_messages

        try:
            response = llm_with_tools.invoke(
                messages,
                config={"configurable": config.get("configurable", {})},
            )
            return {"messages": [response]}
        except Exception as exc:
            import logging
            logging.getLogger(__name__).exception("SqlNode execution failed: %s", exc)
            raise LLMGenerationError(
                f"El asistente de SQL no pudo generar una respuesta: {exc}"
            ) from exc
