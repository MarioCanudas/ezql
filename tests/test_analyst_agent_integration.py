"""End-to-end integration tests for AnalystAgent with sample database execution."""

from unittest.mock import MagicMock, patch
import pytest

from backend.models import AgentReply, Content, Messages, Role
from backend.services.agent.agent import AnalystAgent
from backend.services.user_database import UserDatabase
from langchain_core.messages import AIMessage, HumanMessage, ToolMessage


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

        # Step 1: Orchestrator delegates to SQL Specialist
        # Step 2: SQL Specialist calls execute_advanced_sql tool
        # Step 3: SQL Specialist receives tool output and returns final answer
        mock_llm.bind_tools.return_value = mock_llm
        mock_llm.invoke.side_effect = [
            # 1. Orchestrator response -> delegate to sql
            AIMessage(
                content="",
                tool_calls=[
                    {
                        "name": "delegate_to_sql",
                        "args": {},
                        "id": "call_orch_1",
                        "type": "tool_call",
                    }
                ],
            ),
            # 2. SqlNode response -> execute_advanced_sql
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
            # 3. SqlNode response -> final answer
            AIMessage(
                content="Hay un total de 8,808 títulos en la base de datos de Netflix.",
            ),
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
        )  # type: ignore[call-arg]

        reply = agent.generate_reply(
            user_message=user_message_str,
            history=[db_msg],
            summary=None,
            runtime_db_id=read_db.id,
            user_id=1,
        )

        assert isinstance(reply, AgentReply)
        assert "8,808" in reply.text
        assert reply.data is not None
        assert len(reply.data) > 0  # TableBlock captured from execute_advanced_sql
