from typing import Any
from langchain.agents import create_agent
from langchain_core.runnables import RunnableConfig
from pydantic import ValidationError

from backend.services.agent.state import AgentState, AgentConfiguration
from backend.services.agent.nodes.base import NodeBase
from backend.prompts import SQL_AGENT_SYSTEM_PROMPT
from backend.services.user_database import RuntimeDatabaseError
from backend.services.agent.agent_chat import LLMGenerationError
from backend.services.agent.tools import sql_tools

class SqlNode(NodeBase):
    def __call__(self, state: AgentState, config: RunnableConfig) -> dict[str, Any]:
        """
        SQL Node that uses injected sql_tools
        to answer database-related questions.
        """
        try:
            agent_config = AgentConfiguration.model_validate(config.get("configurable", {}))
        except ValidationError as e:
            raise ValueError(f"Invalid configuration in config['configurable']: {e}")

        # Check if database exists early (Fail Fast)
        try:
            agent_config.database_service.get_schema(agent_config.runtime_db_id, user_id=agent_config.user_id)
        except RuntimeDatabaseError as exc:
            from langchain_core.messages import AIMessage
            return {"messages": [AIMessage(content=str(exc))]}

        llm = agent_config.llm_service._build_client()
        
        agent = create_agent(
            model=llm, tools=sql_tools, system_prompt=SQL_AGENT_SYSTEM_PROMPT
        )
        
        from typing import cast
        try:
            response = agent.invoke(
                cast(Any, {"messages": list(state.messages)}),
                config={"configurable": config.get("configurable", {}), "recursion_limit": 25},
            )
            new_message = response["messages"][-1]
            return {"messages": [new_message]}
        except Exception as exc:
            raise LLMGenerationError(
                "The SQL assistant could not generate a response."
            ) from exc
