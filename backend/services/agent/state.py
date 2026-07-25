from typing import Annotated, Any, Literal
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


SpecialistName = Literal["sql", "statistics", "visualization"]


class ToolArtifact(BaseModel):
    tool_call_id: str
    tool_name: str | None = None
    ok: bool
    summary: str
    data: Any = None
    warnings: list[str] = Field(default_factory=list)
    blocks: list[dict[str, Any]] = Field(default_factory=list)


class ExecutionPlan(BaseModel):
    """Small, ordered plan produced once by the orchestrator for each request."""

    steps: list[SpecialistName] = Field(default_factory=list, max_length=3)
    clarification: str | None = None


class AgentState(BaseModel):
    messages: Annotated[list[BaseMessage], add_messages] = Field(default_factory=list)
    plan: list[SpecialistName] = Field(default_factory=list)
    plan_created: bool = False
    completed_steps: Annotated[list[SpecialistName], append_data] = Field(default_factory=list)
    artifacts: Annotated[list[ToolArtifact], append_data] = Field(default_factory=list)
    processed_tool_call_ids: Annotated[list[str], append_data] = Field(default_factory=list)
    response: dict[str, Any] | None = None
