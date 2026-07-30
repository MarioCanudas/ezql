from __future__ import annotations

from typing import Annotated, Any, Literal

from langchain_core.messages import BaseMessage
from langgraph.graph.message import add_messages
from pydantic import BaseModel, ConfigDict, Field

from backend.models.blocks import UIBlock
from backend.models.metadata import MessageMetadata
from backend.models.statistics import DatasetGrantDescriptor
from backend.services.agent.agent_chat import AgentChat
from backend.services.agent.statistics_grants import StatisticsGrantStore
from backend.services.user_database import UserDatabase


class AgentConfiguration(BaseModel):
    """Runtime-only dependencies passed through LangGraph configurable state."""

    model_config = ConfigDict(arbitrary_types_allowed=True)

    database_service: UserDatabase
    llm_service: AgentChat
    runtime_db_id: str
    user_id: int
    statistics_grants: StatisticsGrantStore = Field(default_factory=StatisticsGrantStore)
    artifact_store: Any | None = None
    input_messages: list[BaseMessage] = Field(default_factory=list)
    thread_id: str | None = None


def append_data(left: list, right: list) -> list:
    return left + right


SpecialistName = Literal["sql", "statistics", "quality", "visualization"]
TaskStatus = Literal["pending", "ready", "running", "completed", "failed", "skipped"]
ResourceClass = Literal["database_read", "statistics_sandbox", "llm", "local"]


class PresentationCandidate(BaseModel):
    """A tool-validated block the orchestrator may select for the final response."""

    id: str
    tool_call_id: str
    block: UIBlock
    fact_keys: list[str] = Field(default_factory=list)


class ToolArtifact(BaseModel):
    """Safe artifact reference stored in graph state.

    ``data`` remains accepted for compatibility with old callers and tests, but
    is explicitly excluded from serialized evidence and is not populated by the
    persistent parent graph. Raw tool payloads belong in the execution-local store.
    """

    tool_call_id: str
    tool_name: str | None = None
    ok: bool
    summary: str
    data: Any = Field(default=None, exclude=True)
    warnings: list[str] = Field(default_factory=list)
    metadata: MessageMetadata = Field(default_factory=dict)
    debug_metadata: MessageMetadata = Field(default_factory=dict, exclude=True)
    presentation_candidates: list[PresentationCandidate] = Field(default_factory=list)


class ResourcePolicy(BaseModel):
    """Deterministic execution policy attached to a planner task."""

    resource: ResourceClass = "database_read"
    parallelizable: bool = True
    max_concurrency: int = Field(default=2, ge=1, le=8)
    requires_previous_result: bool = False


class AgentTask(BaseModel):
    # The planner may omit it in a structured response; normalization assigns
    # a deterministic id before the task enters the executable graph.
    id: str = ""
    specialist: SpecialistName
    objective: str = Field(min_length=1)
    depends_on: list[str] = Field(default_factory=list)
    policy: ResourcePolicy = Field(default_factory=ResourcePolicy)
    status: TaskStatus = "pending"
    attempts: int = Field(default=0, ge=0)
    max_attempts: int = Field(default=2, ge=1, le=2)
    requires_grant: bool = False


# Compatibility name retained for integrations that imported PlanStep directly.
# New code should use AgentTask and dependencies rather than a positional queue.
class ExecutionPlan(BaseModel):
    """DAG proposed by the planner for one investigation round."""

    tasks: list[AgentTask] = Field(default_factory=list, max_length=8)

class OrchestrationDecision(BaseModel):
    action: Literal["continue", "finalize"] = "finalize"
    reason: str = ""
    tasks: list[AgentTask] = Field(default_factory=list, max_length=8)
    summary: str = ""
    narrative: str = ""
    candidate_ids: list[str] = Field(default_factory=list)


# Temporary import aliases for external integrations. Production routing uses AgentTask.
PlanStep = AgentTask
InvestigationDecision = OrchestrationDecision
ResponseSelection = OrchestrationDecision


class SpecialistContribution(BaseModel):
    """Composable, evidence-backed pieces proposed by one specialist."""

    task_id: str = ""
    step_id: str = ""  # Compatibility with the previous queue implementation.
    specialist: SpecialistName
    summary: str
    artifact_ids: list[str] = Field(default_factory=list)
    blocks: list[UIBlock] = Field(default_factory=list)


class TaskResult(BaseModel):
    """Safe result returned from a specialist subgraph to the parent graph."""

    task_id: str
    status: Literal["completed", "failed"]
    specialist: SpecialistName
    summary: str = ""
    artifact_ids: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    error_code: str | None = None


class SpecialistState(BaseModel):
    """Ephemeral state for one specialist subgraph.

    This state is compiled without a checkpointer, so tool messages and raw
    results never enter the durable parent checkpoint.
    """

    model_config = ConfigDict(arbitrary_types_allowed=True)

    messages: Annotated[list[BaseMessage], add_messages] = Field(default_factory=list)
    task: AgentTask
    artifacts: Annotated[list[ToolArtifact], append_data] = Field(default_factory=list)
    processed_tool_call_ids: Annotated[list[str], append_data] = Field(default_factory=list)
    contributions: Annotated[list[SpecialistContribution], append_data] = Field(default_factory=list)
    statistics_grants: Annotated[list[DatasetGrantDescriptor], append_data] = Field(default_factory=list)
    completed: bool = False
    error_code: str | None = None


class AgentState(BaseModel):
    """Durable parent state: control flow and safe evidence references only."""

    model_config = ConfigDict(arbitrary_types_allowed=True)

    # Kept only for old direct node tests. Production graph input leaves it empty;
    # conversation messages travel through runtime configuration and subgraphs.
    messages: Annotated[list[BaseMessage], add_messages] = Field(default_factory=list)
    planning_started: bool = False
    plan_round: int = 0
    replan_count: int = 0
    tasks: list[AgentTask] = Field(default_factory=list)
    task_results: Annotated[list[TaskResult], append_data] = Field(default_factory=list)
    artifacts: Annotated[list[ToolArtifact], append_data] = Field(default_factory=list)
    contributions: Annotated[list[SpecialistContribution], append_data] = Field(default_factory=list)
    statistics_grants: Annotated[list[DatasetGrantDescriptor], append_data] = Field(default_factory=list)
    processed_tool_call_ids: Annotated[list[str], append_data] = Field(default_factory=list)
    active_task: AgentTask | None = None
    response: dict[str, Any] | None = None
    pending_steps: list[AgentTask] = Field(default_factory=list, exclude=True)
    completed_steps: Annotated[list[AgentTask], append_data] = Field(default_factory=list, exclude=True)
