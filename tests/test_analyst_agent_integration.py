"""End-to-end integration tests for AnalystAgent with sample database execution."""

from unittest.mock import MagicMock, patch
import pytest

from backend.models import (
    AgentReply,
    AgentResponse,
    ChartBlock,
    Content,
    MarkdownBlock,
    Messages,
    MetricBlock,
    Role,
)
from backend.services.agent.agent import AnalystAgent
from backend.services.agent.state import (
    ExecutionPlan,
    InvestigationDecision,
    PlanStep,
    SpecialistContribution,
)
from backend.services.user_database import UserDatabase
from langchain_core.messages import AIMessage


@pytest.fixture(name="real_sample_db")
def fixture_real_sample_db():
    db_service = UserDatabase()
    read_db = db_service.register_sample_sqlite(user_id=1)
    yield db_service, read_db
    db_service.close()


class TestAnalystAgentIntegration:
    """Test full agent flow with sample SQLite database."""

    def test_sample_db_query_execution(self, real_sample_db):
        db_service, read_db = real_sample_db

        # Verify that sample database is accessible and has tables
        schema = db_service.get_schema(read_db.id, user_id=1)
        assert len(schema) > 0
        assert schema[0].name == "netflix_titles"

        # Verify database query execution directly
        res = db_service.execute_readonly_query(
            read_db.id, user_id=1, sql="SELECT COUNT(*) AS total FROM netflix_titles"
        )
        assert res.row_count == 1
        assert res.rows[0]["total"] == 8808

    @patch("backend.services.agent.agent_chat.AgentChat._build_client")
    def test_analyst_agent_graph_query_flow(self, mock_build_client, real_sample_db):
        db_service, read_db = real_sample_db

        # Mock LLM calls in graph execution step-by-step
        mock_llm = MagicMock()
        mock_build_client.return_value = mock_llm

        # Step 1: planner creates the SQL plan
        # Step 2: SQL Specialist calls execute_advanced_sql tool
        # Step 3: SQL Specialist finishes analysis
        # Step 4: formatter emits the final block response
        mock_llm.bind_tools.return_value = mock_llm
        mock_llm.invoke.side_effect = [
            # 1. SqlNode response -> execute_advanced_sql
            AIMessage(
                content="",
                tool_calls=[
                    {
                        "name": "execute_advanced_sql",
                        "args": {
                            "sql": "SELECT COUNT(*) AS total FROM netflix_titles"
                        },
                        "id": "call_sql_1",
                        "type": "tool_call",
                    }
                ],
            ),
            # 2. SqlNode response -> final analysis text
            AIMessage(
                content="Hay un total de 8,808 títulos en la base de datos de Netflix.",
            ),
        ]

        planner_llm = MagicMock()
        planner_llm.invoke.return_value = ExecutionPlan(
            steps=[PlanStep(specialist="sql", objective="Contar títulos")]
        )
        contribution_llm = MagicMock()
        contribution_llm.invoke.return_value = SpecialistContribution(
            step_id="", specialist="sql", summary="Total de títulos",
            blocks=[MetricBlock(label="Total Títulos", value="8,808")],
        )
        review_llm = MagicMock()
        review_llm.invoke.return_value = InvestigationDecision(
            action="finalize", reason="La evidencia responde la pregunta."
        )
        formatter_llm = MagicMock()
        formatter_llm.invoke.return_value = AgentResponse(
            summary="Hay 8,808 títulos en Netflix",
            blocks=[
                MetricBlock(label="Total Títulos", value="8,808"),
                MarkdownBlock(content="Hay un total de 8,808 títulos en la base de datos de Netflix.")
            ]
        )
        mock_llm.with_structured_output.side_effect = [
            planner_llm, contribution_llm, review_llm, formatter_llm
        ]

        agent = AnalystAgent(
            database_service=db_service,
            model_name="gpt-4o-mini",
            provider="openai",
            api_key="sk-test-key-123",
        )

        user_message_str = "¿Cuántas películas hay en la base de datos?"
        db_msg = Messages(
            chat_id=1,
            role=Role.user,
            content=Content(text=user_message_str, data=None).model_dump(),
        )

        reply = agent.generate_reply(
            user_message=user_message_str,
            history=[db_msg],
            summary=None,
            runtime_db_id=read_db.id,
            user_id=1,
        )

        assert isinstance(reply, AgentReply)
        assert "8,808" in reply.text
        assert reply.blocks is not None
        assert len(reply.blocks) == 2
        assert reply.data is not None

    @patch("backend.services.agent.agent_chat.AgentChat._build_client")
    def test_visualization_retries_without_tool_choice_and_returns_chart(
        self, mock_build_client, real_sample_db
    ):
        """Thinking-compatible retry must execute a real chart tool end to end."""
        db_service, read_db = real_sample_db
        mock_llm = MagicMock()
        mock_llm.bind_tools.return_value = mock_llm
        mock_llm.invoke.side_effect = [
            # Initial response incorrectly avoids tools; the visualization node retries.
            AIMessage(content="No puedo generar una gráfica."),
            AIMessage(
                content="",
                tool_calls=[
                    {
                        "name": "create_line_chart",
                        "args": {
                            "table_name": "netflix_titles",
                            "x_column": "release_year",
                            "y_column": "duration",
                            "title": "Duración promedio de películas por década",
                            "aggregation": "average",
                            "bucket_size": 10,
                            "numeric_prefix": True,
                            "filter_column": "type",
                            "filter_value": "Movie",
                        },
                        "id": "call_chart_1",
                        "type": "tool_call",
                    }
                ],
            ),
            AIMessage(content="La duración promedio varía entre décadas."),
        ]
        mock_build_client.return_value = mock_llm

        planner_llm = MagicMock()
        planner_llm.invoke.return_value = ExecutionPlan(
            steps=[PlanStep(specialist="visualization", objective="Mostrar tendencia de duración")]
        )
        contribution_llm = MagicMock()
        contribution_llm.invoke.return_value = SpecialistContribution(
            step_id="",
            specialist="visualization",
            summary="Tendencia de duración por década.",
            blocks=[MarkdownBlock(content="Tendencia de duración por década.")],
        )
        review_llm = MagicMock()
        review_llm.invoke.return_value = InvestigationDecision(
            action="finalize", reason="La gráfica y la evidencia responden la solicitud."
        )
        formatter_llm = MagicMock()
        formatter_llm.invoke.return_value = AgentResponse(summary="Duración por década.")
        mock_llm.with_structured_output.side_effect = [
            planner_llm,
            contribution_llm,
            review_llm,
            formatter_llm,
        ]

        agent = AnalystAgent(
            database_service=db_service,
            model_name="deepseek-v4",
            provider="deepseek",
            api_key="test-key",
            reasoning_effort="medium",
        )
        reply = agent.generate_reply(
            user_message="Analiza la duración de las películas por década.",
            history=[],
            summary=None,
            runtime_db_id=read_db.id,
            user_id=1,
        )

        assert any(isinstance(block, ChartBlock) for block in reply.blocks or [])
        assert any(artifact["data"].get("chart") for artifact in reply.data or [])
        assert mock_llm.invoke.call_count == 3
        assert all(
            call.kwargs == {"parallel_tool_calls": False}
            for call in mock_llm.bind_tools.call_args_list
        )
