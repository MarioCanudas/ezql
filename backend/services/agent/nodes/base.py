from abc import ABC, abstractmethod
from typing import Any
from backend.services.agent.state import AgentState
from langchain_core.runnables import RunnableConfig


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
