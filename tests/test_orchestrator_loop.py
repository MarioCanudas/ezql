from unittest.mock import MagicMock, patch
from langchain_core.runnables import RunnableConfig

from langchain_core.messages import AIMessage, HumanMessage, ToolMessage

from backend.models.blocks import AgentResponse, MarkdownBlock, MetricBlock
from backend.models.metadata import MetadataValue
from backend.services.agent.agent_chat import AgentChat
from backend.services.agent.nodes.orchestrator import (
    OrchestratorNode,
    _contribution_blocks,
    _enforce_statistics_step,
    _enforce_visualization_step,
)
from backend.services.agent.nodes.artifacts import ArtifactCollectorNode
from backend.services.agent.metadata import MISSING_VALUE, safe_template
from backend.services.agent.nodes.visualization import VisualizationNode
from backend.services.agent.state import (
    AgentState,
    InvestigationDecision,
    PlanStep,
    SpecialistContribution,
    PresentationCandidate,
    ResponseSelection,
    ToolArtifact,
)
from backend.services.user_database import UserDatabase


def _config(database: UserDatabase, runtime_db_id: str) -> RunnableConfig:
    return {
        "configurable": {
            "database_service": database,
            "llm_service": AgentChat(model_name="gpt-4o-mini", api_key="test-key"),
            "runtime_db_id": runtime_db_id,
            "user_id": 1,
        }
    }


@patch("backend.services.agent.agent_chat.AgentChat._build_client")
def test_orchestrator_enqueues_a_complementary_plan(mock_build_client):
    database = UserDatabase()
    try:
        runtime = database.register_sample_sqlite(user_id=1)
        llm = MagicMock()
        review = MagicMock()
        review.invoke.return_value = InvestigationDecision(
            action="continue",
            reason="Falta segmentar la caída.",
            tasks=[PlanStep(specialist="sql", objective="Comparar categorías por período")],
        )
        llm.with_structured_output.return_value = review
        mock_build_client.return_value = llm

        result = OrchestratorNode()(
            AgentState(planning_started=True, plan_round=1),
            _config(database, runtime.id),
        )

        assert result["replan_count"] == 1
        assert result["plan_round"] == 2
        assert result["tasks"][0].specialist == "sql"
        assert result["tasks"][0].objective == "Comparar categorías por período"
    finally:
        database.close()


@patch("backend.services.agent.agent_chat.AgentChat._build_client")
def test_orchestrator_finalizes_after_maximum_replans(mock_build_client):
    database = UserDatabase()
    try:
        runtime = database.register_sample_sqlite(user_id=1)
        llm = MagicMock()
        formatter = MagicMock()
        formatter.invoke.return_value = AgentResponse(summary="Evidencia disponible.")
        llm.with_structured_output.return_value = formatter
        mock_build_client.return_value = llm

        result = OrchestratorNode()(
            AgentState(planning_started=True, plan_round=3, replan_count=2),
            _config(database, runtime.id),
        )

        assert result["response"]["summary"] == "Evidencia disponible."
        assert result["response"]["blocks"][0]["type"] == "markdown"
    finally:
        database.close()


def test_verified_chart_is_preserved_when_specialist_omits_the_block():
    """A successful chart tool call is renderable even if the LLM omits it."""
    state = AgentState(
        artifacts=[
            ToolArtifact(
                tool_call_id="chart-1",
                tool_name="create_line_chart",
                ok=True,
                summary="Visualización preparada.",
                data={
                    "chart": {
                        "chart_type": "line",
                        "title": "Duración promedio por década",
                        "x_axis": "década",
                        "y_axis": ["duración_promedio"],
                        "data": [{"década": "1990", "duración_promedio": 101}],
                    }
                },
            )
        ],
        contributions=[
            SpecialistContribution(
                step_id="round-1-1-visualization",
                specialist="visualization",
                summary="La duración promedio aumentó.",
                blocks=[MarkdownBlock(content="La duración promedio aumentó.")],
            )
        ],
    )

    blocks = _contribution_blocks(state)

    assert [block["type"] for block in blocks] == ["markdown", "chart"]
    assert blocks[1]["title"] == "Duración promedio por década"


def test_explicit_chart_request_always_includes_sql_and_visualization_steps():
    steps = _enforce_visualization_step(
        [],
        [HumanMessage(content="Grafica la tendencia de duración de películas por década")],
    )

    assert [step.specialist for step in steps] == ["sql", "visualization"]


def test_statistical_intent_cannot_be_planned_as_sql_only():
    steps = _enforce_statistics_step(
        [PlanStep(specialist="sql", objective="Consultar ventas")],
        [HumanMessage(content="¿Cuál es la tendencia mensual y el promedio de ventas?")],
    )

    assert [step.specialist for step in steps] == ["sql", "statistics"]


def test_statistical_chart_orders_evidence_before_visualization():
    steps = _enforce_statistics_step(
        _enforce_visualization_step(
            [], [HumanMessage(content="Grafica la evolución y distribución de ventas")]
        ),
        [HumanMessage(content="Grafica la evolución y distribución de ventas")],
    )

    assert [step.specialist for step in steps] == ["sql", "statistics", "visualization"]


def test_quality_intent_cannot_be_planned_without_the_quality_specialist():
    from backend.services.agent.nodes.orchestrator import _required_tasks_for_request

    steps = _required_tasks_for_request(
        [PlanStep(specialist="sql", objective="Inspeccionar tablas")],
        [HumanMessage(content="¿Qué tan completos están los datos y qué columnas tienen valores faltantes?")],
    )

    assert {step.specialist for step in steps} >= {"sql", "quality"}


@patch("backend.services.agent.agent_chat.AgentChat._build_client")
def test_schema_fallback_keeps_explicit_statistics_and_visualization_requests(mock_build_client):
    """A provider without json_schema must not degrade this request to SQL only."""
    database = UserDatabase()
    try:
        runtime = database.register_sample_sqlite(user_id=1)

        class StructuredResult:
            def __init__(self, method: str):
                self.method = method

            def invoke(self, messages, config=None):
                if self.method == "json_schema":
                    raise RuntimeError("json_schema unsupported")
                assert "json" in str(messages[-1].content).casefold()
                return {
                    "tasks": [
                        {
                            "specialist": "sql",
                            "objective": "Resumir la base disponible.",
                        }
                    ]
                }

        class ProviderClient:
            def with_structured_output(self, schema, method="json_schema"):
                assert schema.__name__ == "ExecutionPlan"
                return StructuredResult(method)

        mock_build_client.return_value = ProviderClient()
        result = OrchestratorNode()(
            AgentState(messages=[HumanMessage(
                content="Hazme un resumen de la base de datos con estadísticas y gráficas."
            )]),
            _config(database, runtime.id),
        )

        tasks = {task.specialist: task for task in result["tasks"]}
        assert set(tasks) == {"sql", "statistics", "visualization"}
        assert tasks["visualization"].depends_on == [tasks["sql"].id]
    finally:
        database.close()


def test_artifact_catalog_keeps_only_presentable_facts_and_provenance():
    state = AgentState(
        messages=[
            ToolMessage(
                content=(
                    '{"ok": true, "summary": "Conteo disponible.", "data": '
                    '{"total": 42, "suggested_blocks": [{"type": "metric", '
                    '"label": "Total", "value": "42", "delta": null}]}}'
                ),
                tool_call_id="call-count",
                name="count_rows",
            )
        ]
    )

    update = ArtifactCollectorNode()(state, {})
    metadata = update["artifacts"][0].metadata

    assert len(metadata) == 1
    fact = next(iter(metadata.values()))
    assert fact.value == "42"
    assert fact.artifact_id == "call-count"
    assert update["artifacts"][0].presentation_candidates[0].fact_keys == list(metadata)


def test_template_preserves_natural_narrative_and_replaces_only_invalid_reference():
    assert safe_template("El total es 42", {}) == "El total es 42"
    assert safe_template("El total es {{meta.call-count.data.total}}", {
        "call-count.data.total": MagicMock(),
    }) == "El total es {{meta.call-count.data.total}}"
    assert safe_template("Total {{meta.inexistente}}; tendencia estable.", {}) == (
        f"Total {MISSING_VALUE}; tendencia estable."
    )


def test_invalid_candidate_selection_falls_back_to_verified_candidates_in_order():
    metadata = {
        "call-1.fact.total.0": MetadataValue(
            value="42", display="42", artifact_id="call-1", path="data.suggested_blocks.0.value"
        )
    }
    candidate = PresentationCandidate(
        id="call-1.block.0",
        tool_call_id="call-1",
        block=MetricBlock(label="Total", value="{{meta.call-1.fact.total.0}}"),
        fact_keys=["call-1.fact.total.0"],
    )
    from backend.services.agent.nodes.orchestrator import _selected_presentation

    blocks, selected = _selected_presentation(
        [candidate], ResponseSelection(summary="Hay datos.", candidate_ids=["no-existe"]), metadata
    )

    assert blocks == [candidate.block]
    assert selected == metadata


@patch("backend.services.agent.agent_chat.AgentChat._build_client")
def test_orchestrator_uses_only_selected_verified_candidates(mock_build_client):
    database = UserDatabase()
    try:
        runtime = database.register_sample_sqlite(user_id=1)
        metadata = {
            "call-1.fact.total.0": MetadataValue(
                value="42", display="42", artifact_id="call-1", path="data.suggested_blocks.0.value"
            )
        }
        first = PresentationCandidate(
            id="call-1.block.0",
            tool_call_id="call-1",
            block=MetricBlock(label="Total", value="{{meta.call-1.fact.total.0}}"),
            fact_keys=["call-1.fact.total.0"],
        )
        second = PresentationCandidate(
            id="call-1.block.1",
            tool_call_id="call-1",
            block=MarkdownBlock(content="Bloque verificado."),
        )
        selection_llm = MagicMock()
        selection_llm.invoke.return_value = ResponseSelection(
            summary="El total es {{meta.call-1.fact.total.0}}.",
            narrative="Resultado verificado.",
            candidate_ids=[second.id, first.id],
        )
        llm = MagicMock()
        llm.with_structured_output.return_value = selection_llm
        mock_build_client.return_value = llm

        result = OrchestratorNode()(
            AgentState(
                planning_started=True,
                plan_round=3,
                replan_count=2,
                artifacts=[
                    ToolArtifact(
                        tool_call_id="call-1",
                        ok=True,
                        summary="Resultado disponible.",
                        metadata=metadata,
                        presentation_candidates=[first, second],
                    )
                ],
            ),
            _config(database, runtime.id),
        )

        assert result["response"]["summary"] == "El total es {{meta.call-1.fact.total.0}}."
        assert [block["type"] for block in result["response"]["blocks"]] == [
            "markdown", "markdown", "metric"
        ]
        assert result["response"]["metadata"] == {
            key: value.model_dump() for key, value in metadata.items()
        }
    finally:
        database.close()


@patch("backend.services.agent.agent_chat.AgentChat._build_client")
def test_visualization_uses_compatible_tool_binding(mock_build_client):
    database = UserDatabase()
    try:
        runtime = database.register_sample_sqlite(user_id=1)
        llm = MagicMock()
        bound_llm = MagicMock()
        llm.bind_tools.return_value = bound_llm
        bound_llm.invoke.return_value = AIMessage(
            content="",
            tool_calls=[{"name": "create_line_chart", "args": {}, "id": "chart-1"}],
        )
        mock_build_client.return_value = llm

        result = VisualizationNode()(
            AgentState(
                messages=[HumanMessage(content="Muéstrame una gráfica")],
                    tasks=[PlanStep(specialist="visualization", objective="Crear gráfica")],
            ),
            _config(database, runtime.id),
        )

        assert result["messages"][0].tool_calls
        assert llm.bind_tools.call_args.kwargs == {"parallel_tool_calls": False}
    finally:
        database.close()
