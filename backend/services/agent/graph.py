from __future__ import annotations

from typing import Any

from langgraph.graph import END, START, StateGraph
from langgraph.prebuilt import ToolNode
from langchain_core.runnables import RunnableConfig
from langgraph.types import Send

from backend.services.agent.nodes.artifacts import ArtifactCollectorNode
from backend.services.agent.nodes.base import NodeBase
from backend.services.agent.nodes.statistics_grant import StatisticsGrantNode
from backend.services.agent.state import (
    AgentState,
    AgentTask,
    SpecialistState,
    TaskResult,
    TaskStatus,
    ToolArtifact,
    SpecialistContribution,
)
from backend.services.agent.tools import (
    quality_tools,
    sql_tools,
    statistics_tools,
    visualization_tools,
)


def route_tool_calls(state: Any) -> str:
    """Compatibility router for direct specialist-node tests."""

    if not getattr(state, "messages", None):
        return "next"
    return "tools" if getattr(state.messages[-1], "tool_calls", []) else "next"


def _terminal(status: TaskStatus) -> bool:
    return status in {"completed", "failed", "skipped"}


def _result_by_task(state: AgentState) -> dict[str, TaskResult]:
    results: dict[str, TaskResult] = {}
    for raw in state.task_results:
        result = raw if isinstance(raw, TaskResult) else TaskResult.model_validate(raw)
        results[result.task_id] = result
    return results


def ready_tasks(state: AgentState) -> list[AgentTask]:
    """Return dependency-satisfied tasks, respecting deterministic policies."""

    results = _result_by_task(state)
    completed_ids = {
        task.id
        for task in state.tasks
        if task.status == "completed" or results.get(task.id, None) and results[task.id].status == "completed"
    }
    selected: list[AgentTask] = []
    resource_counts: dict[str, int] = {}
    for task in state.tasks:
        if task.status not in {"pending", "ready"}:
            continue
        if task.id in results and results[task.id].status == "completed":
            continue
        if any(dependency not in completed_ids for dependency in task.depends_on):
            continue
        resource = task.policy.resource
        limit = task.policy.max_concurrency if task.policy.parallelizable else 1
        if resource_counts.get(resource, 0) >= limit:
            continue
        resource_counts[resource] = resource_counts.get(resource, 0) + 1
        selected.append(task.model_copy(update={"status": "ready"}))
    return selected


def route_after_orchestrator(state: AgentState) -> str:
    """Route the parent graph to a dynamic task dispatch or completion."""

    if state.response:
        return "end"
    if state.tasks:
        return "dispatch" if ready_tasks(state) else "orchestrator"

    # Backwards-compatible route for callers still constructing the old queue.
    pending_steps = getattr(state, "pending_steps", [])
    if pending_steps:
        if pending_steps[0].specialist == "statistics":
            return "authorize_statistics"
        return pending_steps[0].specialist
    return "orchestrator"


def dispatch_tasks(state: AgentState) -> list[Send] | str:
    tasks = ready_tasks(state)
    if not tasks:
        return "orchestrator"
    return [Send("task_worker", {"active_task": task.model_dump()}) for task in tasks]


def _local_tool_route(state: SpecialistState) -> str:
    if state.messages and getattr(state.messages[-1], "tool_calls", []):
        return "tools"
    return "end"


def _compile_specialist_graph(
    specialist: NodeBase,
    tools: list[Any],
    *,
    grant_node: StatisticsGrantNode | None = None,
):
    """Compile an ephemeral specialist subgraph.

    Tool messages and raw payloads exist only inside this invocation. The parent
    graph receives safe artifact references and contributions from the result.
    """

    workflow = StateGraph(SpecialistState)
    workflow.add_node("specialist", specialist)
    workflow.add_node("tools", ToolNode(tools))
    workflow.add_node("collect", ArtifactCollectorNode())
    if grant_node is not None:
        workflow.add_node("authorize", grant_node)
        workflow.add_edge(START, "authorize")
        workflow.add_edge("authorize", "specialist")
    else:
        workflow.add_edge(START, "specialist")
    workflow.add_conditional_edges(
        "specialist", _local_tool_route, {"tools": "tools", "end": END}
    )
    workflow.add_edge("tools", "collect")
    workflow.add_edge("collect", "specialist")
    return workflow.compile(checkpointer=False)


def _subgraph_result(
    task: AgentTask,
    result: dict[str, Any],
) -> dict[str, Any]:
    artifacts = [
        item if isinstance(item, ToolArtifact) else ToolArtifact.model_validate(item)
        for item in result.get("artifacts", [])
    ]
    contributions = [
        item if isinstance(item, SpecialistContribution) else SpecialistContribution.model_validate(item)
        for item in result.get("contributions", [])
    ]
    artifact_ids = [artifact.tool_call_id for artifact in artifacts if artifact.ok]
    summary = contributions[-1].summary if contributions else "Etapa completada."
    return {
        "task_results": [
            TaskResult(
                task_id=task.id,
                status="completed" if result.get("completed", False) else "failed",
                specialist=task.specialist,
                summary=summary,
                artifact_ids=artifact_ids,
                warnings=[warning for artifact in artifacts for warning in artifact.warnings],
                error_code=result.get("error_code"),
            )
        ],
        "artifacts": artifacts,
        "contributions": contributions,
        "statistics_grants": result.get("statistics_grants", []),
    }


def create_agent_graph(
    orchestrator_node: NodeBase,
    sql_node: NodeBase,
    statistics_node: NodeBase,
    statistics_grant_node: StatisticsGrantNode,
    visualization_node: NodeBase,
    quality_node: NodeBase | None = None,
    *,
    checkpointer: Any | None = None,
):
    """Build the durable parent graph and ephemeral specialist subgraphs."""

    quality_node = quality_node or sql_node
    specialist_graphs = {
        "sql": _compile_specialist_graph(sql_node, sql_tools),
        "statistics": _compile_specialist_graph(
            statistics_node, statistics_tools, grant_node=statistics_grant_node
        ),
        "quality": _compile_specialist_graph(quality_node, quality_tools),
        "visualization": _compile_specialist_graph(visualization_node, visualization_tools),
    }

    def task_worker(state: AgentState, config: RunnableConfig) -> dict[str, Any]:
        active_task = state.get("active_task") if isinstance(state, dict) else state.active_task
        if active_task is None:
            return {}
        task = active_task if isinstance(active_task, AgentTask) else AgentTask.model_validate(active_task)
        try:
            input_messages = []
            configurable = config.get("configurable", {}) if config else {}
            input_messages = configurable.get("input_messages", [])
            local_state = SpecialistState(task=task, messages=list(input_messages))
            result = specialist_graphs[task.specialist].invoke(
                local_state,
                config=config,
            )
            return _subgraph_result(task, result)
        except Exception as exc:
            return {
                "task_results": [
                    TaskResult(
                        task_id=task.id,
                        status="failed",
                        specialist=task.specialist,
                        summary="La etapa no pudo completarse.",
                        error_code=type(exc).__name__,
                    )
                ]
            }

    workflow = StateGraph(AgentState)
    workflow.add_node("orchestrator", orchestrator_node)
    workflow.add_node("dispatch", lambda state, config: {})
    workflow.add_node("task_worker", task_worker)
    # Stable node names retained for graph introspection and older integrations.
    # Runtime dispatch uses the task_worker and specialist subgraphs above.
    workflow.add_node("sql", sql_node)
    workflow.add_node("statistics", statistics_node)
    workflow.add_node("authorize_statistics", statistics_grant_node)
    workflow.add_node("visualization", visualization_node)
    workflow.add_node("quality", quality_node)
    workflow.add_node("tools_sql", ToolNode(sql_tools))
    workflow.add_node("tools_statistics", ToolNode(statistics_tools))
    workflow.add_node("tools_visualization", ToolNode(visualization_tools))
    workflow.add_node("tools_quality", ToolNode(quality_tools))
    workflow.add_node("collect_sql", ArtifactCollectorNode())
    workflow.add_node("collect_statistics", ArtifactCollectorNode())
    workflow.add_node("collect_visualization", ArtifactCollectorNode())
    workflow.add_node("collect_quality", ArtifactCollectorNode())
    workflow.add_edge(START, "orchestrator")
    workflow.add_conditional_edges(
        "orchestrator",
        route_after_orchestrator,
        {
            "dispatch": "dispatch",
            "orchestrator": "orchestrator",
            # Compatibility routes for direct old queue states.
            "sql": "task_worker",
            "statistics": "task_worker",
            "authorize_statistics": "task_worker",
            "visualization": "task_worker",
            "end": END,
        },
    )
    workflow.add_conditional_edges(
        "dispatch", dispatch_tasks, ["task_worker", "orchestrator"]
    )
    workflow.add_edge("task_worker", "orchestrator")
    return workflow.compile(checkpointer=checkpointer)
