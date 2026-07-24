"""Shared fixtures for the EzQL backend test suite."""

from __future__ import annotations

from collections.abc import Generator
from unittest.mock import MagicMock

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.pool import StaticPool
from sqlmodel import Session, SQLModel, create_engine

from backend.main import app
from backend.models import (
    Chats,
    Content,
    Engines,
    Messages,
    Models,
    Role,
    Users,
)
from backend.services.user_database import UserDatabase
from backend.utils.dependencies import get_runtime_database_service, get_session


# ---------------------------------------------------------------------------
# Database fixtures
# ---------------------------------------------------------------------------


@pytest.fixture(name="engine")
def fixture_engine():
    """Create an in-memory SQLite engine with all tables.

    ``check_same_thread=False`` is required because FastAPI's TestClient
    runs the ASGI app in a background thread while the test itself runs
    in the main thread — both need access to the same in-memory DB.
    """
    engine = create_engine(
        "sqlite://",
        echo=False,
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    SQLModel.metadata.create_all(engine)
    yield engine
    engine.dispose()


@pytest.fixture(name="session")
def fixture_session(engine) -> Generator[Session, None, None]:
    """Provide a session scoped to each test."""
    with Session(engine) as session:
        yield session


# ---------------------------------------------------------------------------
# Service mocks
# ---------------------------------------------------------------------------


@pytest.fixture(name="mock_runtime_db_service")
def fixture_mock_runtime_db_service() -> UserDatabase:
    """A mocked UserDatabase that doesn't need real SQLite files."""
    mock = MagicMock(spec=UserDatabase)
    mock.get_database.return_value = {
        "id": "test-runtime-db",
        "display_name": "Test DB",
        "user_id": 1,
    }
    return mock


# ---------------------------------------------------------------------------
# FastAPI TestClient
# ---------------------------------------------------------------------------


@pytest.fixture(name="client")
def fixture_client(
    session: Session,
    mock_runtime_db_service: UserDatabase,
) -> Generator[TestClient, None, None]:
    """FastAPI TestClient with dependency overrides."""

    def _override_session():
        yield session

    def _override_runtime_db():
        return mock_runtime_db_service

    app.dependency_overrides[get_session] = _override_session
    app.dependency_overrides[get_runtime_database_service] = _override_runtime_db

    with TestClient(app, raise_server_exceptions=False) as test_client:
        yield test_client

    app.dependency_overrides.clear()


# ---------------------------------------------------------------------------
# Seed data fixtures
# ---------------------------------------------------------------------------


@pytest.fixture(name="seed_engine")
def fixture_seed_engine(session: Session) -> Engines:
    """Pre-seeded database engine."""
    engine = Engines(name="sqlite3", is_supported=True)  # type: ignore[call-arg]
    session.add(engine)
    session.commit()
    session.refresh(engine)
    return engine


@pytest.fixture(name="seed_user")
def fixture_seed_user(session: Session) -> Users:
    """Pre-seeded user with API keys configured."""
    user = Users(
        name="testuser",
        hashed_password="hashed",
        openai_api_key="sk-test-key-123",
        deepseek_api_key=None,
    )  # type: ignore[call-arg]
    session.add(user)
    session.commit()
    session.refresh(user)
    return user


@pytest.fixture(name="seed_model")
def fixture_seed_model(session: Session) -> Models:
    """Pre-seeded LLM model."""
    model = Models(
        name="gpt-4o-mini",
        company="openai",
    )  # type: ignore[call-arg]
    session.add(model)
    session.commit()
    session.refresh(model)
    return model


@pytest.fixture(name="seed_chat")
def fixture_seed_chat(
    session: Session,
    seed_user: Users,
    seed_model: Models,
) -> Chats:
    """Pre-seeded chat linked to user, model, and a runtime DB."""
    chat = Chats(
        title="Test Chat",
        user_id=seed_user.id,  # type: ignore[arg-type]
        model_id=seed_model.id,  # type: ignore[arg-type]
        runtime_db_id="test-runtime-db",
    )  # type: ignore[call-arg]
    session.add(chat)
    session.commit()
    session.refresh(chat)
    return chat


@pytest.fixture(name="seed_messages")
def fixture_seed_messages(
    session: Session,
    seed_chat: Chats,
) -> list[Messages]:
    """Pre-seeded conversation with 2 messages."""
    user_msg = Messages(
        chat_id=seed_chat.id,  # type: ignore[arg-type]
        role=Role.user,
        content=Content(text="Hello", data=None).model_dump(),
    )  # type: ignore[call-arg]
    agent_msg = Messages(
        chat_id=seed_chat.id,  # type: ignore[arg-type]
        role=Role.assistant,
        content=Content(text="Hi there!", data=None).model_dump(),
    )  # type: ignore[call-arg]
    session.add(user_msg)
    session.add(agent_msg)
    session.commit()
    session.refresh(user_msg)
    session.refresh(agent_msg)
    return [user_msg, agent_msg]
