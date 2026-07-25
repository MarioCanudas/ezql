from unittest.mock import MagicMock, patch

from langchain_core.messages import AIMessage, HumanMessage

from backend.models.blocks import AgentResponse, MarkdownBlock
from backend.services.agent.agent_chat import AgentChat
from backend.services.agent.nodes.orchestrator import (
    OrchestratorNode,
    _contribution_blocks,
    _enforce_visualization_step,
)
from backend.services.agent.nodes.visualization import VisualizationNode
from backend.services.agent.state import (
    AgentState,
    InvestigationDecision,
    PlanStep,
    SpecialistContribution,
    ToolArtifact,
)
from backend.services.user_database import UserDatabase


def _config(database: UserDatabase, runtime_db_id: str) -> dict:
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
            steps=[PlanStep(specialist="sql", objective="Comparar categorías por período")],
        )
        llm.with_structured_output.return_value = review
        mock_build_client.return_value = llm

        result = OrchestratorNode()(
            AgentState(planning_started=True, plan_round=1),
            _config(database, runtime.id),
        )

        assert result["replan_count"] == 1
        assert result["plan_round"] == 2
        assert result["pending_steps"][0].specialist == "sql"
        assert result["pending_steps"][0].objective == "Comparar categorías por período"
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
                pending_steps=[PlanStep(specialist="visualization", objective="Crear gráfica")],
            ),
            _config(database, runtime.id),
        )

        assert result["messages"][0].tool_calls
        assert llm.bind_tools.call_args.kwargs == {"parallel_tool_calls": False}
    finally:
        database.close()
