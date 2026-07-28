from backend.services.agent.nodes.orchestrator import (
    _apply_task_results,
    validate_task_plan,
)
from backend.services.agent.graph import ready_tasks
from backend.services.agent.state import AgentState, AgentTask, ResourcePolicy, TaskResult, ToolArtifact


def test_ready_tasks_fan_out_independent_work_and_hold_dependencies():
    state = AgentState(
        tasks=[
            AgentTask(id="data", specialist="sql", objective="Preparar datos"),
            AgentTask(id="trend", specialist="statistics", objective="Analizar tendencia", depends_on=["data"]),
            AgentTask(id="quality", specialist="quality", objective="Revisar calidad"),
        ]
    )

    assert {task.id for task in ready_tasks(state)} == {"data", "quality"}


def test_ready_tasks_respects_database_read_concurrency_limit():
    state = AgentState(
        tasks=[
            AgentTask(id=f"sql-{index}", specialist="sql", objective=f"Consulta {index}")
            for index in range(3)
        ]
    )

    assert len(ready_tasks(state)) == 2


def test_plan_validator_removes_cycles_and_clamps_resource_policy():
    tasks = validate_task_plan([
        AgentTask(id="a", specialist="sql", objective="A", depends_on=["b"]),
        AgentTask(id="b", specialist="statistics", objective="B", depends_on=["a"]),
        AgentTask(
            id="sandbox",
            specialist="statistics",
            objective="Sandbox",
            policy=ResourcePolicy(resource="statistics_sandbox", max_concurrency=8),
        ),
    ])

    assert {task.id for task in tasks} == {"sandbox"}
    assert tasks[0].requires_grant is True
    assert tasks[0].policy.max_concurrency == 1


def test_plan_validator_repairs_visualization_without_evidence_dependency():
    tasks = validate_task_plan([
        AgentTask(
            id="chart",
            specialist="visualization",
            objective="Mostrar la evolución",
        )
    ])

    chart = next(task for task in tasks if task.id == "chart")
    assert any(task.specialist == "sql" for task in tasks)
    assert chart.depends_on
    assert chart.depends_on[0] in {task.id for task in tasks}


def test_raw_artifact_data_is_excluded_from_durable_model_dump():
    artifact = ToolArtifact(
        tool_call_id="call-1",
        ok=True,
        summary="Resultado",
        data={"rows": [{"secret": "internal"}]},
    )

    assert "data" not in artifact.model_dump()


def test_failed_task_is_retried_once_then_marked_failed():
    state = AgentState(
        tasks=[AgentTask(id="read", specialist="sql", objective="Leer datos")],
        task_results=[
            TaskResult(task_id="read", status="failed", specialist="sql")
        ],
    )

    retry = _apply_task_results(state)
    assert retry[0].status == "ready"
    assert retry[0].attempts == 1

    exhausted = _apply_task_results(
        state.model_copy(update={"tasks": retry})
    )
    assert exhausted[0].status == "failed"
    assert exhausted[0].attempts == 2


def test_fallback_sql_task_has_required_dag_id():
    tasks = validate_task_plan([
        AgentTask(
            id="round-1-1-sql",
            specialist="sql",
            objective="Descubrir los datos necesarios.",
        )
    ])

    assert tasks[0].id == "round-1-1-sql"
