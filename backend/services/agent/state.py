from typing import Annotated, Any, Literal
from pydantic import BaseModel, Field, ConfigDict
from langchain_core.messages import BaseMessage
from langgraph.graph.message import add_messages
from backend.services.user_database import UserDatabase
from backend.services.agent.agent_chat import AgentChat
from backend.models.blocks import UIBlock


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
class PlanStep(BaseModel):
    id: str = ""
    specialist: SpecialistName
    objective: str = Field(min_length=1)


class ExecutionPlan(BaseModel):
    """Ordered work proposed by the orchestrator for one investigation round."""

    steps: list[PlanStep] = Field(default_factory=list, max_length=3)


class InvestigationDecision(BaseModel):
    action: Literal["continue", "finalize"]
    reason: str
    steps: list[PlanStep] = Field(default_factory=list, max_length=3)


class SpecialistContribution(BaseModel):
    """Composable, evidence-backed pieces proposed by one specialist."""

    step_id: str
    specialist: SpecialistName
    summary: str
    artifact_ids: list[str] = Field(default_factory=list)
    blocks: list[UIBlock] = Field(default_factory=list)


class AgentState(BaseModel):
    messages: Annotated[list[BaseMessage], add_messages] = Field(default_factory=list)
    planning_started: bool = False
    plan_round: int = 0
    replan_count: int = 0
    pending_steps: list[PlanStep] = Field(default_factory=list)
    completed_steps: Annotated[list[PlanStep], append_data] = Field(default_factory=list)
    artifacts: Annotated[list[ToolArtifact], append_data] = Field(default_factory=list)
    processed_tool_call_ids: Annotated[list[str], append_data] = Field(default_factory=list)
    contributions: Annotated[list[SpecialistContribution], append_data] = Field(default_factory=list)
    response: dict[str, Any] | None = None
