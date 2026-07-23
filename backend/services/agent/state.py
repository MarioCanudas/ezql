from typing import Annotated, Any
from pydantic import BaseModel, Field, ConfigDict
from langchain_core.messages import BaseMessage
from langgraph.graph.message import add_messages
from backend.services.user_database import UserDatabase
from backend.services.agent.agent_chat import AgentChat


class AgentConfiguration(BaseModel):
    """
    Type-safe configuration for the agent graph dependencies.
    """

    model_config = ConfigDict(arbitrary_types_allowed=True)

    database_service: UserDatabase
    llm_service: AgentChat
    runtime_db_id: str
    user_id: int


def append_data(left: list, right: list) -> list:
    return left + right


class AgentState(BaseModel):
    messages: Annotated[list[BaseMessage], add_messages] = Field(default_factory=list)
    query_data: Annotated[list[Any], append_data] = Field(default_factory=list)
