"""Tests for the chats router — CRUD and the critical reply endpoint."""

from unittest.mock import MagicMock, patch

from fastapi.testclient import TestClient
from sqlmodel import Session

from backend.models import AgentReply, Chats, MetricBlock, Models, Users
from backend.services.agent.agent_chat import LLMGenerationError


# ---------------------------------------------------------------------------
# Chat CRUD
# ---------------------------------------------------------------------------


class TestChatCRUD:
    def test_create_chat_valid(
        self,
        client: TestClient,
        seed_user: Users,
        seed_model: Models,
    ):
        payload = {
            "user_id": seed_user.id,
            "model_id": seed_model.id,
            "title": "New Chat",
            "runtime_db_id": "test-runtime-db",
        }
        response = client.post("/api/v1/chats", json=payload)
        assert response.status_code == 201
        data = response.json()
        assert data["title"] == "New Chat"
        assert data["user_id"] == seed_user.id

    def test_create_chat_nonexistent_user(
        self,
        client: TestClient,
        seed_model: Models,
    ):
        payload = {
            "user_id": 99999,
            "model_id": seed_model.id,
            "title": "Test",
            "runtime_db_id": "test-runtime-db",
        }
        response = client.post("/api/v1/chats", json=payload)
        assert response.status_code == 404

    def test_create_chat_no_db_returns_400(
        self,
        client: TestClient,
        seed_user: Users,
        seed_model: Models,
    ):
        payload = {
            "user_id": seed_user.id,
            "model_id": seed_model.id,
            "title": "No DB Chat",
            # no db_id and no runtime_db_id
        }
        response = client.post("/api/v1/chats", json=payload)
        assert response.status_code == 400

    def test_get_chat(self, client: TestClient, seed_chat: Chats):
        response = client.get(f"/api/v1/chats/{seed_chat.id}")
        assert response.status_code == 200
        assert response.json()["id"] == seed_chat.id

    def test_get_chat_not_found(self, client: TestClient):
        response = client.get("/api/v1/chats/99999")
        assert response.status_code == 404

    def test_update_chat_title(self, client: TestClient, seed_chat: Chats):
        response = client.patch(
            f"/api/v1/chats/{seed_chat.id}",
            json={"title": "Updated Title"},
        )
        assert response.status_code == 200
        assert response.json()["title"] == "Updated Title"

    def test_delete_chat_and_messages(
        self,
        client: TestClient,
        seed_chat: Chats,
        seed_messages,
    ):
        # Verify messages exist first
        msgs = client.get(f"/api/v1/chats/{seed_chat.id}/messages")
        assert len(msgs.json()) == 2

        # Delete
        response = client.delete(f"/api/v1/chats/{seed_chat.id}")
        assert response.status_code == 204

        # Chat should be gone
        get_resp = client.get(f"/api/v1/chats/{seed_chat.id}")
        assert get_resp.status_code == 404

    def test_list_chats_filtered_by_user(
        self,
        client: TestClient,
        seed_chat: Chats,
        seed_user: Users,
    ):
        response = client.get(f"/api/v1/chats?user_id={seed_user.id}")
        assert response.status_code == 200
        data = response.json()
        assert len(data) >= 1
        assert all(c["user_id"] == seed_user.id for c in data)


# ---------------------------------------------------------------------------
# Reply endpoint (POST /chats/{chat_id}/reply)
# ---------------------------------------------------------------------------


class TestChatReply:
    """Tests for the agent reply endpoint with mocked LLM services."""

    @patch("backend.routers.chats.AnalystAgent")
    def test_reply_success(
        self,
        mock_agent_cls,
        client: TestClient,
        seed_chat: Chats,
    ):
        mock_instance = MagicMock()
        mock_instance.generate_reply.return_value = AgentReply(
            text="Agent answer", data=None
        )
        mock_instance.llm_service.summarize_chat.return_value = "Summary"
        mock_agent_cls.return_value = mock_instance

        payload = {"content": {"text": "What are total sales?", "data": None}}
        response = client.post(f"/api/v1/chats/{seed_chat.id}/reply", json=payload)

        assert response.status_code == 201
        data = response.json()
        assert "user_message" in data
        assert "assistant_message" in data
        assert data["user_message"]["content"]["text"] == "What are total sales?"
        assert data["assistant_message"]["content"]["text"] == "Agent answer"

    @patch("backend.routers.chats.AnalystAgent")
    def test_reply_persists_messages(
        self,
        mock_agent_cls,
        client: TestClient,
        seed_chat: Chats,
    ):
        mock_instance = MagicMock()
        mock_instance.generate_reply.return_value = AgentReply(text="Answer", data=None)
        mock_instance.llm_service.summarize_chat.return_value = "Summary"
        mock_agent_cls.return_value = mock_instance

        payload = {"content": {"text": "Question", "data": None}}
        client.post(f"/api/v1/chats/{seed_chat.id}/reply", json=payload)

        # Messages should now be in the DB
        msgs = client.get(f"/api/v1/chats/{seed_chat.id}/messages")
        data = msgs.json()
        assert len(data) == 2  # user + assistant
        assert data[0]["role"] == "user"
        assert data[1]["role"] == "agent"

    @patch("backend.routers.chats.AnalystAgent")
    def test_reply_does_not_persist_raw_execution_payloads(
        self,
        mock_agent_cls,
        client: TestClient,
        seed_chat: Chats,
    ):
        mock_instance = MagicMock()
        mock_instance.generate_reply.return_value = AgentReply(
            text="Respuesta verificada",
            blocks=[MetricBlock(label="Total", value="42")],
            data=[{"ok": True, "data": {"rows_preview": [{"secret": "internal"}]}}],
        )
        mock_instance.llm_service.summarize_chat.return_value = "Summary"
        mock_agent_cls.return_value = mock_instance

        payload = {"content": {"text": "¿Cuántos registros hay?", "data": None}}
        response = client.post(f"/api/v1/chats/{seed_chat.id}/reply", json=payload)

        assert response.status_code == 201
        assistant = response.json()["assistant_message"]["content"]
        assert assistant["data"] is None
        assert assistant["blocks"][0]["type"] == "metric"

    def test_reply_empty_content_returns_400(
        self,
        client: TestClient,
        seed_chat: Chats,
    ):
        payload = {"content": {"text": "   ", "data": None}}
        response = client.post(f"/api/v1/chats/{seed_chat.id}/reply", json=payload)
        assert response.status_code == 400

    def test_reply_nonexistent_chat_returns_404(self, client: TestClient):
        payload = {"content": {"text": "hello", "data": None}}
        response = client.post("/api/v1/chats/99999/reply", json=payload)
        assert response.status_code == 404

    def test_reply_wrong_user_returns_400(
        self,
        client: TestClient,
        seed_chat: Chats,
    ):
        payload = {
            "content": {"text": "hello", "data": None},
            "user_id": 99999,  # Wrong user
        }
        response = client.post(f"/api/v1/chats/{seed_chat.id}/reply", json=payload)
        assert response.status_code == 400

    def test_reply_missing_api_key_returns_400(
        self,
        client: TestClient,
        session: Session,
        seed_chat: Chats,
    ):
        # Remove the API key from the user
        user = session.get(Users, seed_chat.user_id)
        assert user is not None
        user.openai_api_key = None
        session.add(user)
        session.commit()

        payload = {"content": {"text": "hello", "data": None}}
        response = client.post(f"/api/v1/chats/{seed_chat.id}/reply", json=payload)
        assert response.status_code == 400

    @patch("backend.routers.chats.AnalystAgent")
    def test_reply_llm_error_returns_502(
        self,
        mock_agent_cls,
        client: TestClient,
        seed_chat: Chats,
    ):
        mock_instance = MagicMock()
        mock_instance.generate_reply.side_effect = LLMGenerationError("Failed")
        mock_agent_cls.return_value = mock_instance

        payload = {"content": {"text": "hello", "data": None}}
        response = client.post(f"/api/v1/chats/{seed_chat.id}/reply", json=payload)
        assert response.status_code == 502

    @patch("backend.routers.chats.AnalystAgent")
    def test_summary_failure_is_non_fatal(
        self,
        mock_agent_cls,
        client: TestClient,
        seed_chat: Chats,
    ):
        """If the summary LLM call fails, the response should still be returned."""
        mock_instance = MagicMock()
        mock_instance.generate_reply.return_value = AgentReply(
            text="Success response", data=None
        )
        mock_instance.llm_service.summarize_chat.side_effect = Exception(
            "Summary LLM failed"
        )
        mock_agent_cls.return_value = mock_instance

        payload = {"content": {"text": "hello", "data": None}}
        response = client.post(f"/api/v1/chats/{seed_chat.id}/reply", json=payload)

        # Response should succeed despite summary failure
        assert response.status_code == 201
        assert response.json()["assistant_message"]["content"]["text"] == "Success response"
