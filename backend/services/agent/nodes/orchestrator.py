from typing import Any
from langchain_core.messages import SystemMessage
from langchain_core.runnables import RunnableConfig
from pydantic import ValidationError

from backend.services.agent.state import AgentState, AgentConfiguration
from backend.services.agent.nodes.base import NodeBase
from backend.services.agent.tools import orchestrator_tools
from backend.prompts.orchestrator import ORCHESTRATOR_SYSTEM_PROMPT


class OrchestratorNode(NodeBase):
    def __call__(self, state: AgentState, config: RunnableConfig) -> dict[str, Any]:
        """
        Orchestrator Node that routes user requests to the appropriate specialist.
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
        llm_with_tools = llm.bind_tools(orchestrator_tools)

        messages = [SystemMessage(content=ORCHESTRATOR_SYSTEM_PROMPT)] + list(state.messages)

        try:
            response = llm_with_tools.invoke(
                messages,
                config={"configurable": config.get("configurable", {})},
            )
            return {"messages": [response]}
        except Exception as exc:
            import logging
            logging.getLogger(__name__).exception("OrchestratorNode execution failed: %s", exc)
            from backend.services.agent.agent_chat import LLMGenerationError
            raise LLMGenerationError(
                f"El orquestador no pudo procesar la solicitud: {exc}"
            ) from exc
