import os
from collections.abc import Sequence
from typing import Any

import httpx
from langchain_core.messages import AIMessage, HumanMessage, SystemMessage
from langchain_core.runnables import RunnableConfig
from langchain_openai import ChatOpenAI
from pydantic import BaseModel, ConfigDict, PrivateAttr, SecretStr, field_validator

from backend.models import Content, LLMProviderConfig, Messages, Role
from backend.prompts import DEFAULT_SYSTEM_PROMPT, SUMMARY_SYSTEM_PROMPT


class LLMConfigurationError(RuntimeError):
    pass


class LLMGenerationError(RuntimeError):
    pass


PROVIDER_CONFIGS = {
    "openai": LLMProviderConfig(
        name="OpenAI",
        base_url_env="OPENAI_BASE_URL",
    ),
    "deepseek": LLMProviderConfig(
        name="DeepSeek",
        default_base_url="https://api.deepseek.com",
        base_url_env="DEEPSEEK_BASE_URL",
    ),
}


PROVIDER_ALIASES = {
    "open ai": "openai",
    "openai": "openai",
    "deep seek": "deepseek",
    "deep_seek": "deepseek",
    "deepseek": "deepseek",
}


def resolve_llm_provider(provider: str | None, model_name: str) -> str:
    normalized_provider = (provider or "").strip().casefold()
    if normalized_provider in PROVIDER_ALIASES:
        return PROVIDER_ALIASES[normalized_provider]

    normalized_model = model_name.strip().casefold()
    if normalized_model.startswith("deepseek"):
        return "deepseek"

    return "openai"


MODEL_ALIASES = {
    "deepseek-chat": "deepseek-v4-flash",
    "deepseek-coder": "deepseek-v4-flash",
}


def resolve_llm_model_name(model_name: str) -> str:
    normalized = (model_name or "").strip().casefold()
    return MODEL_ALIASES.get(normalized, model_name)


class AgentChat(BaseModel):
    model_config = ConfigDict(frozen=True)

    model_name: str
    provider: str | None = None
    api_key: str | None = None
    temperature: float = 0.2
    reasoning_effort: str | None = None
    system_prompt: str = DEFAULT_SYSTEM_PROMPT
    _client: ChatOpenAI | None = PrivateAttr(default=None)
    _http_client: httpx.Client | None = PrivateAttr(default=None)

    def with_http_client(self, client: httpx.Client | None) -> "AgentChat":
        clone = self.model_copy()
        clone._http_client = client
        return clone

    @field_validator("api_key")
    @classmethod
    def validate_api_key(cls, v: str | None) -> str | None:
        if v is not None and not v.strip():
            raise ValueError("API key cannot be empty or just whitespace.")
        return v

    def _history_messages(self, history: Sequence[Messages]):
        messages = []
        for entry in history:
            content = Content.model_validate(entry.content).text
            if entry.role == Role.user:
                messages.append(HumanMessage(content=content))
            elif entry.role == Role.assistant:
                messages.append(AIMessage(content=content))
        return messages

    def _build_messages(
        self,
        history: Sequence[Messages],
        *,
        summary: str | None = None,
    ):
        messages = []
        if self.system_prompt:
            messages.append(SystemMessage(content=self.system_prompt))
        if summary:
            messages.append(
                SystemMessage(
                    content=(
                        "Resumen persistente de este chat para mantener contexto: "
                        f"{summary}"
                    )
                )
            )
        messages.extend(self._history_messages(history))
        return messages

    def _get_provider_config(self) -> LLMProviderConfig:
        provider_key = resolve_llm_provider(self.provider, self.model_name)
        return PROVIDER_CONFIGS[provider_key]

    def _build_client(self) -> ChatOpenAI:
        if self._client is not None:
            return self._client
        config = self._get_provider_config()
        api_key = (self.api_key or "").strip()
        if not api_key:
            raise LLMConfigurationError(
                f"Missing {config.name} API key in your profile configuration."
            )

        base_url = None
        if config.base_url_env:
            base_url = os.getenv(config.base_url_env)
        if not base_url:
            base_url = config.default_base_url

        resolved_model = resolve_llm_model_name(self.model_name)
        provider_key = resolve_llm_provider(self.provider, self.model_name)
        model_lower = resolved_model.strip().casefold()
        is_reasoning_model = (
            model_lower.startswith(("o1", "o3"))
            or "reasoner" in model_lower
            or "r1" in model_lower
        )

        client_kwargs: dict[str, Any] = {
            "model": resolved_model,
            "api_key": SecretStr(api_key),
            "base_url": base_url,
        }

        if not is_reasoning_model:
            client_kwargs["temperature"] = self.temperature

        effort = self.reasoning_effort
        if not effort and is_reasoning_model and provider_key == "openai":
            effort = "medium"

        if effort:
            client_kwargs["reasoning_effort"] = effort
        if self._http_client is not None:
            client_kwargs["http_client"] = self._http_client
        self._client = ChatOpenAI(**client_kwargs)
        return self._client

    def bind_tools(self, tools: list[Any], *, parallel_tool_calls: bool = False):
        return self._build_client().bind_tools(tools, parallel_tool_calls=parallel_tool_calls)

    def invoke_structured(self, schema: type[BaseModel], messages: list[Any], *, config: RunnableConfig, label: str):
        try:
            return self._build_client().with_structured_output(schema, method="json_schema").invoke(messages, config=config)
        except Exception as exc:
            import logging
            logging.getLogger(__name__).warning("Structured %s output with json_schema failed; retrying json_mode (%s)", label, type(exc).__name__)
            # Some OpenAI-compatible providers require the literal word "JSON"
            # in the prompt when response_format=json_object is used. Keep this
            # guarantee in the shared fallback instead of relying on every
            # structured-output prompt to remember it.
            json_mode_messages = [
                *messages,
                SystemMessage(
                    content=(
                        "Devuelve exclusivamente un objeto JSON válido que cumpla "
                        "el esquema solicitado."
                    )
                ),
            ]
            return self._build_client().with_structured_output(schema, method="json_mode").invoke(
                json_mode_messages,
                config=config,
            )

    def _message_text(self, response_content) -> str:
        if isinstance(response_content, str):
            return response_content
        return str(response_content)

    def generate_reply(
        self,
        history: Sequence[Messages],
        *,
        summary: str | None = None,
    ) -> str:
        client = self._build_client()
        try:
            response = client.invoke(self._build_messages(history, summary=summary))
        except Exception as exc:
            import logging
            logging.getLogger(__name__).exception("AgentChat LLM invocation failed: %s", exc)
            raise LLMGenerationError(
                f"Error en la llamada al modelo LLM: {exc}"
            ) from exc

        return self._message_text(response.content)

    def summarize_chat(
        self,
        history: Sequence[Messages],
        *,
        current_summary: str | None = None,
    ) -> str:
        client = self._build_client()
        messages = [SystemMessage(content=SUMMARY_SYSTEM_PROMPT)]
        if current_summary:
            messages.append(
                SystemMessage(content=f"Resumen anterior del chat: {current_summary}")
            )
        messages.extend(self._history_messages(history))

        try:
            response = client.invoke(messages)
        except Exception as exc:
            raise LLMGenerationError("The chat summary could not be updated.") from exc

        return self._message_text(response.content).strip()
