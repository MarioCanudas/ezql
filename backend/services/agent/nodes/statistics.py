from typing import Any
from langchain_core.messages import AIMessage
from langchain_core.runnables import RunnableConfig

from backend.services.agent.state import AgentState
from backend.services.agent.nodes.base import NodeBase


class StatisticsNode(NodeBase):
    def __call__(self, state: AgentState, config: RunnableConfig) -> dict[str, Any]:
        """
        Placeholder node for statistical analysis.
        In the future, this node will handle statistical tasks.
        """
        message = AIMessage(content="[Statistics Node Placeholder]")
        return {"messages": [message]}
