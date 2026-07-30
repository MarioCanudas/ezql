"""Contract tests for a reply's persistence and execution lifecycle."""

from unittest.mock import MagicMock, patch

from fastapi.testclient import TestClient
from sqlmodel import Session, select

from backend.models import AgentReply, AgentRuns, Chats, Messages, Role
from backend.services.agent.agent_chat import LLMGenerationError


def _reply_payload(text: str = "¿Cuántos títulos hay?") -> dict:
    return {"content": {"text": text, "data": None}}


@patch("backend.routers.chats.AnalystAgent")
def test_completed_reply_records_a_linked_execution_run(
    agent_class: MagicMock,
    client: TestClient,
    session: Session,
    seed_chat: Chats,
) -> None:
    agent = agent_class.return_value
    agent.generate_reply.return_value = AgentReply(text="Hay 8,807 títulos.")

    response = client.post(f"/api/v1/chats/{seed_chat.id}/reply", json=_reply_payload())

    assert response.status_code == 201
    user_message_id = response.json()["user_message"]["id"]
    run = session.exec(select(AgentRuns)).one()
    assert run.status == "completed"
    assert run.message_id == user_message_id
    assert run.chat_id == seed_chat.id
    assert run.thread_id == f"chat:{seed_chat.id}:message:{user_message_id}"
    assert run.completed_at is not None


@patch("backend.routers.chats.AnalystAgent")
def test_failed_reply_keeps_a_failed_run_without_creating_an_assistant_message(
    agent_class: MagicMock,
    client: TestClient,
    session: Session,
    seed_chat: Chats,
) -> None:
    agent_class.return_value.generate_reply.side_effect = LLMGenerationError("provider unavailable")

    response = client.post(f"/api/v1/chats/{seed_chat.id}/reply", json=_reply_payload())

    assert response.status_code == 502
    run = session.exec(select(AgentRuns)).one()
    assert run.status == "failed"
    assert run.error_code == "LLMGenerationError"
    assert run.completed_at is not None
    messages = session.exec(select(Messages).where(Messages.chat_id == seed_chat.id)).all()
    assert [message.role for message in messages] == [Role.user]


@patch("backend.routers.chats.AnalystAgent")
def test_reply_history_excludes_messages_already_covered_by_summary(
    agent_class: MagicMock,
    client: TestClient,
    session: Session,
    seed_chat: Chats,
    seed_messages: list[Messages],
) -> None:
    covered_message = seed_messages[-1]
    assert covered_message.id is not None
    seed_chat.summary = "Contexto anterior resumido"
    seed_chat.summary_through_message_id = covered_message.id
    session.add(seed_chat)
    session.commit()

    agent = agent_class.return_value
    agent.generate_reply.return_value = AgentReply(text="Respuesta nueva")

    response = client.post(
        f"/api/v1/chats/{seed_chat.id}/reply",
        json=_reply_payload("Pregunta nueva"),
    )

    assert response.status_code == 201
    history = agent.generate_reply.call_args.kwargs["history"]
    assert [message.content["text"] for message in history] == ["Pregunta nueva"]
    assert agent.generate_reply.call_args.kwargs["summary"] == "Contexto anterior resumido"

