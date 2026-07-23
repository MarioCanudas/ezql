from typing import Any
from langchain_core.messages import SystemMessage
from langchain_core.runnables import RunnableConfig

from backend.services.agent.state import AgentState, AgentConfiguration
from backend.services.agent.nodes.base import NodeBase
from backend.services.agent.tools import statistics_tools
from backend.prompts.statistics_agent import STATISTICS_AGENT_SYSTEM_PROMPT


class StatisticsNode(NodeBase):
    def __call__(self, state: AgentState, config: RunnableConfig) -> dict[str, Any]:
        """
        Statistics Node powered by an LLM with access to statistics tools.
        """
        try:
            agent_config = AgentConfiguration.model_validate(config.get("configurable", {}))
        except Exception:
            return {"messages": []}

        # Bind tools to LLM
        llm_with_tools = agent_config.llm_service.bind_tools(statistics_tools)

        # Assemble prompt with system message
        messages = [SystemMessage(content=STATISTICS_AGENT_SYSTEM_PROMPT)] + list(state.messages)

        # Invoke LLM
        response = llm_with_tools.invoke(messages)

        return {"messages": [response]}
