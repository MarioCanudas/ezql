"""Tests for the messages router (GET / POST /chats/{chat_id}/messages)."""

from fastapi.testclient import TestClient

from backend.models import Chats


class TestListMessages:
    def test_empty_chat(self, client: TestClient, seed_chat: Chats):
        response = client.get(f"/api/v1/chats/{seed_chat.id}/messages")
        assert response.status_code == 200
        assert response.json() == []

    def test_with_messages(self, client: TestClient, seed_chat: Chats, seed_messages):
        response = client.get(f"/api/v1/chats/{seed_chat.id}/messages")
        assert response.status_code == 200
        data = response.json()
        assert len(data) == 2
        assert data[0]["chat_id"] == seed_chat.id

    def test_nonexistent_chat_returns_404(self, client: TestClient):
        response = client.get("/api/v1/chats/99999/messages")
        assert response.status_code == 404

    def test_pagination_limit(self, client: TestClient, seed_chat: Chats, seed_messages):
        response = client.get(f"/api/v1/chats/{seed_chat.id}/messages?limit=1&offset=0")
        assert response.status_code == 200
        data = response.json()
        assert len(data) == 1

    def test_pagination_offset(self, client: TestClient, seed_chat: Chats, seed_messages):
        resp1 = client.get(f"/api/v1/chats/{seed_chat.id}/messages?limit=1&offset=0")
        resp2 = client.get(f"/api/v1/chats/{seed_chat.id}/messages?limit=1&offset=1")
        assert resp1.status_code == 200
        assert resp2.status_code == 200
        data1 = resp1.json()
        data2 = resp2.json()
        assert len(data1) == 1
        assert len(data2) == 1
        assert data1[0]["id"] != data2[0]["id"]

    def test_messages_are_chronological(self, client: TestClient, seed_chat: Chats, seed_messages):
        response = client.get(f"/api/v1/chats/{seed_chat.id}/messages")
        data = response.json()
        assert len(data) == 2
        # First message should be user, second should be agent
        assert data[0]["role"] == "user"
        assert data[1]["role"] == "agent"


class TestCreateMessage:
    def test_valid_user_message(self, client: TestClient, seed_chat: Chats):
        payload = {
            "role": "user",
            "content": {"text": "What are the sales?", "data": None},
        }
        response = client.post(f"/api/v1/chats/{seed_chat.id}/messages", json=payload)
        assert response.status_code == 201
        data = response.json()
        assert data["role"] == "user"
        assert data["content"]["text"] == "What are the sales?"
        assert data["chat_id"] == seed_chat.id

    def test_nonexistent_chat_returns_404(self, client: TestClient):
        payload = {
            "role": "user",
            "content": {"text": "hello", "data": None},
        }
        response = client.post("/api/v1/chats/99999/messages", json=payload)
        assert response.status_code == 404

    def test_created_message_appears_in_list(self, client: TestClient, seed_chat: Chats):
        payload = {
            "role": "user",
            "content": {"text": "New message", "data": None},
        }
        client.post(f"/api/v1/chats/{seed_chat.id}/messages", json=payload)

        response = client.get(f"/api/v1/chats/{seed_chat.id}/messages")
        assert response.status_code == 200
        data = response.json()
        assert any(m["content"]["text"] == "New message" for m in data)
