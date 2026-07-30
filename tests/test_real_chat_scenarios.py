"""Real end-to-end chat scenarios using the locally configured test account.

The FastAPI application, database and sample SQLite data are all temporary and
local.  Only the configured DeepSeek provider is external: no LLM, node or
agent method is mocked in these tests.
"""

from __future__ import annotations

import os
import uuid
from collections.abc import Generator
from pathlib import Path
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.pool import StaticPool
from sqlmodel import Session, SQLModel, create_engine, select

from backend.main import app
from backend.models import AgentRuns, Chats, Models, Users
from backend.services.agent.checkpoint import AgentCheckpointStore
from backend.services.agent.runtime import AgentRuntime
from backend.services.db_connection import DBConnection
from backend.services.user_database import UserDatabase
from backend.utils.dependencies import ServiceRegistry, get_runtime_database_service, get_session


pytestmark = [
    pytest.mark.real_agent,
    pytest.mark.skipif(
        os.getenv("EZQL_RUN_REAL_AGENT_TESTS") != "1",
        reason="run-test enables real agent scenarios; set EZQL_RUN_REAL_AGENT_TESTS=1 manually to run them.",
    ),
]


@pytest.fixture(name="real_chat_client")
def fixture_real_chat_client(tmp_path: Path) -> Generator[tuple[TestClient, Session, AgentRuntime], None, None]:
    """Provide a disposable API application backed by the real test account key."""
    source_connection = DBConnection()
    source_connection.connect()
    assert source_connection.engine is not None
    with Session(source_connection.engine) as source_session:
        test_user = source_session.exec(
            select(Users).where(Users.name == "test1")
        ).one_or_none()
        assert test_user is not None, "The local test user 'test1' is required."
        assert test_user.deepseek_api_key, "The local test user needs a DeepSeek API key."
        api_key = test_user.deepseek_api_key

    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    SQLModel.metadata.create_all(engine)
    session = Session(engine)
    user = Users(
        name="real-agent-test",
        hashed_password="not-used-by-this-api-test",
        deepseek_api_key=api_key,
    )
    model = Models(name="deepseek-chat", company="DeepSeek")
    session.add(user)
    session.add(model)
    session.commit()
    session.refresh(user)
    session.refresh(model)
    assert user.id is not None
    assert model.id is not None

    database_service = UserDatabase(temp_root=tmp_path / "runtime-databases")
    runtime_database = database_service.register_sample_sqlite(
        user_id=user.id,
        runtime_id=f"real-agent-netflix-{uuid.uuid4().hex}",
    )
    chat = Chats(
        title="Real agent scenario",
        user_id=user.id,
        model_id=model.id,
        runtime_db_id=runtime_database.id,
    )
    session.add(chat)
    session.commit()
    session.refresh(chat)

    checkpoints = AgentCheckpointStore(tmp_path / "agent-checkpoints.db")
    runtime = AgentRuntime(checkpoints)

    def override_session() -> Generator[Session, None, None]:
        yield session

    app.dependency_overrides[get_session] = override_session
    app.dependency_overrides[get_runtime_database_service] = lambda: database_service
    with patch.object(ServiceRegistry, "get_agent_runtime", return_value=runtime):
        with TestClient(app, raise_server_exceptions=False) as client:
            yield client, session, runtime

    app.dependency_overrides.clear()
    runtime.close()
    checkpoints.close()
    database_service.close()
    session.close()
    engine.dispose()


@pytest.mark.parametrize(
    ("prompt", "expected_specialists"),
    [
        (
            "¿Cómo ha evolucionado la cantidad de títulos de Netflix con el tiempo y qué tendencia se observa?",
            {"sql", "statistics"},
        ),
        (
            "Muéstrame una gráfica de los títulos agregados por año y explica el cambio más importante.",
            {"sql", "visualization"},
        ),
        (
            "¿Qué tan completos están los datos y qué columnas tienen valores faltantes?",
            {"quality"},
        ),
    ],
)
def test_real_prompt_reaches_the_model_and_activates_expected_nodes(
    real_chat_client: tuple[TestClient, Session, AgentRuntime],
    prompt: str,
    expected_specialists: set[str],
) -> None:
    client, session, runtime = real_chat_client
    chat = session.exec(select(Chats)).one()
    assert chat.id is not None

    response = client.post(
        f"/api/v1/chats/{chat.id}/reply",
        json={"content": {"text": prompt, "data": None}, "user_id": chat.user_id},
    )

    assert response.status_code == 201, response.text
    payload = response.json()
    assert payload["user_message"]["content"]["text"] == prompt
    assert payload["assistant_message"]["content"]["text"].strip()
    assert "select " not in payload["assistant_message"]["content"]["text"].casefold()

    run = session.exec(select(AgentRuns)).one()
    assert run.status == "completed"
    state = runtime.graph.get_state({"configurable": {"thread_id": run.thread_id}})
    records = [
        *state.values.get("tasks", []),
        *state.values.get("task_results", []),
        *state.values.get("contributions", []),
    ]
    activated_specialists = {
        record.specialist if hasattr(record, "specialist") else record["specialist"]
        for record in records
    }
    assert expected_specialists.issubset(activated_specialists)
