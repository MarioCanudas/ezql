from typing import Any
from langchain_core.messages import AIMessage
from langchain_core.runnables import RunnableConfig

from backend.services.agent.state import AgentState
from backend.services.agent.nodes.base import NodeBase


class VisualizationNode(NodeBase):
    def __call__(self, state: AgentState, config: RunnableConfig) -> dict[str, Any]:
        """
        Placeholder node for data visualization.
        In the future, this node will handle plotting and chart specifications.
        """
        message = AIMessage(content="[Visualization Node Placeholder]")
        return {"messages": [message]}
