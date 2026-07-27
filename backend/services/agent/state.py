from typing import Annotated, Any, Literal
from pydantic import BaseModel, Field, ConfigDict
from langchain_core.messages import BaseMessage
from langgraph.graph.message import add_messages
from backend.services.user_database import UserDatabase
from backend.services.agent.agent_chat import AgentChat
from backend.models.blocks import UIBlock
from backend.models.metadata import MessageMetadata
from backend.models.statistics import DatasetGrantDescriptor
from backend.services.agent.statistics_grants import StatisticsGrantStore


class AgentConfiguration(BaseModel):
    """
    Type-safe configuration for the agent graph dependencies.
    """

    model_config = ConfigDict(arbitrary_types_allowed=True)

    database_service: UserDatabase
    llm_service: AgentChat
    runtime_db_id: str
    user_id: int
    statistics_grants: StatisticsGrantStore = Field(default_factory=StatisticsGrantStore)


def append_data(left: list, right: list) -> list:
    return left + right


SpecialistName = Literal["sql", "statistics", "visualization"]


class PresentationCandidate(BaseModel):
    """A tool-validated block the orchestrator may select for the final response."""

    id: str
    tool_call_id: str
    block: UIBlock
    fact_keys: list[str] = Field(default_factory=list)


class ToolArtifact(BaseModel):
    tool_call_id: str
    tool_name: str | None = None
    ok: bool
    summary: str
    data: Any = None
    warnings: list[str] = Field(default_factory=list)
    # Semantic facts are the only metadata exposed to the LLM and UI.
    metadata: MessageMetadata = Field(default_factory=dict)
    # Flattened values remain available for internal diagnosis only.
    debug_metadata: MessageMetadata = Field(default_factory=dict, exclude=True)
    presentation_candidates: list[PresentationCandidate] = Field(default_factory=list)


class ResponseSelection(BaseModel):
    """LLM-selected, evidence-backed composition of a final response."""

    summary: str
    narrative: str = ""
    candidate_ids: list[str] = Field(default_factory=list)


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
    statistics_grants: Annotated[list[DatasetGrantDescriptor], append_data] = Field(default_factory=list)
    response: dict[str, Any] | None = None
