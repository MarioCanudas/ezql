"""Tests for the AgentChat service and provider resolution."""

import pytest
from langchain_core.messages import AIMessage, HumanMessage, SystemMessage

from backend.models import Content, Messages, Role
from backend.services.agent.agent_chat import AgentChat, resolve_llm_provider


# ---------------------------------------------------------------------------
# resolve_llm_provider
# ---------------------------------------------------------------------------


class TestResolveLLMProvider:
    def test_openai_exact(self):
        assert resolve_llm_provider("openai", "gpt-4") == "openai"

    def test_openai_case_insensitive(self):
        assert resolve_llm_provider("OpenAI", "gpt-4") == "openai"

    def test_openai_with_space(self):
        assert resolve_llm_provider("open ai", "gpt-4") == "openai"

    def test_deepseek_exact(self):
        assert resolve_llm_provider("deepseek", "deepseek-chat") == "deepseek"

    def test_deepseek_with_space(self):
        assert resolve_llm_provider("Deep Seek", "any-model") == "deepseek"

    def test_deepseek_underscore(self):
        assert resolve_llm_provider("deep_seek", "any-model") == "deepseek"

    def test_none_provider_with_deepseek_model(self):
        assert resolve_llm_provider(None, "deepseek-chat") == "deepseek"

    def test_none_provider_with_gpt_model(self):
        assert resolve_llm_provider(None, "gpt-4") == "openai"

    def test_unknown_provider_defaults_to_openai(self):
        assert resolve_llm_provider("unknown_provider", "some-model") == "openai"

    def test_empty_string_provider_defaults_to_openai(self):
        assert resolve_llm_provider("", "gpt-4o") == "openai"


# ---------------------------------------------------------------------------
# AgentChat API key validation
# ---------------------------------------------------------------------------


class TestAgentChatValidation:
    def test_empty_key_raises(self):
        with pytest.raises(ValueError, match="empty"):
            AgentChat(model_name="gpt-4", provider="openai", api_key="")

    def test_whitespace_key_raises(self):
        with pytest.raises(ValueError, match="empty"):
            AgentChat(model_name="gpt-4", provider="openai", api_key="   ")

    def test_none_key_accepted(self):
        chat = AgentChat(model_name="gpt-4", provider="openai", api_key=None)
        assert chat.api_key is None

    def test_valid_key_accepted(self):
        chat = AgentChat(model_name="gpt-4", provider="openai", api_key="sk-valid")
        assert chat.api_key == "sk-valid"

    def test_openai_reasoning_model_build_client(self):
        chat = AgentChat(model_name="o3-mini", provider="openai", api_key="sk-test")
        client = chat._build_client()
        assert getattr(client, "reasoning_effort", None) == "medium"
        assert getattr(client, "temperature", None) is None or getattr(client, "temperature", None) == 1.0

    def test_deepseek_reasoner_build_client(self):
        chat = AgentChat(model_name="deepseek-reasoner", provider="deepseek", api_key="sk-test")
        client = chat._build_client()
        assert client.model_name == "deepseek-reasoner"
        assert client.openai_api_base == "https://api.deepseek.com"

    def test_custom_reasoning_effort(self):
        chat = AgentChat(
            model_name="gpt-4o",
            provider="openai",
            api_key="sk-test",
            reasoning_effort="high",
        )
        client = chat._build_client()
        assert getattr(client, "reasoning_effort", None) == "high"


# ---------------------------------------------------------------------------
# _history_messages
# ---------------------------------------------------------------------------


def _make_db_message(role: Role, text: str) -> Messages:
    """Create a Messages instance without DB persistence."""
    return Messages(
        chat_id=1,
        role=role,
        content=Content(text=text, data=None).model_dump(),
    )  # type: ignore[call-arg]


class TestHistoryMessages:
    def test_converts_user_and_agent_messages(self):
        chat = AgentChat(model_name="gpt-4", provider="openai", api_key="sk-test")
        history = [
            _make_db_message(Role.user, "Hi"),
            _make_db_message(Role.assistant, "Hello!"),
        ]
        result = chat._history_messages(history)

        assert len(result) == 2
        assert isinstance(result[0], HumanMessage)
        assert result[0].content == "Hi"
        assert isinstance(result[1], AIMessage)
        assert result[1].content == "Hello!"

    def test_empty_history(self):
        chat = AgentChat(model_name="gpt-4", provider="openai", api_key="sk-test")
        result = chat._history_messages([])
        assert result == []


# ---------------------------------------------------------------------------
# _build_messages
# ---------------------------------------------------------------------------


class TestBuildMessages:
    def test_includes_system_prompt(self):
        chat = AgentChat(
            model_name="gpt-4",
            provider="openai",
            api_key="sk-test",
            system_prompt="You are helpful.",
        )
        result = chat._build_messages([], summary=None)

        assert len(result) == 1
        assert isinstance(result[0], SystemMessage)
        assert result[0].content == "You are helpful."

    def test_includes_summary(self):
        chat = AgentChat(
            model_name="gpt-4",
            provider="openai",
            api_key="sk-test",
            system_prompt="System",
        )
        result = chat._build_messages([], summary="Previous context")

        assert len(result) == 2
        assert isinstance(result[1], SystemMessage)
        assert "Previous context" in result[1].content

    def test_includes_history(self):
        chat = AgentChat(
            model_name="gpt-4",
            provider="openai",
            api_key="sk-test",
            system_prompt="System",
        )
        history = [_make_db_message(Role.user, "Question?")]
        result = chat._build_messages(history, summary=None)

        assert len(result) == 2  # system + user message
        assert isinstance(result[1], HumanMessage)
        assert result[1].content == "Question?"

    def test_full_stack(self):
        chat = AgentChat(
            model_name="gpt-4",
            provider="openai",
            api_key="sk-test",
            system_prompt="System",
        )
        history = [
            _make_db_message(Role.user, "Q"),
            _make_db_message(Role.assistant, "A"),
        ]
        result = chat._build_messages(history, summary="Summary")

        # system + summary + 2 history
        assert len(result) == 4
