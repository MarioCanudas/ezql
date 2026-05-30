import os
from collections.abc import Sequence
from dataclasses import dataclass

from langchain_core.messages import AIMessage, HumanMessage, SystemMessage
from langchain_openai import ChatOpenAI
from pydantic import SecretStr

from backend.models import Content, Messages, Role

DEFAULT_SYSTEM_PROMPT = (
    "Eres un analista de datos para usuarios de negocio. Responde en espanol claro "
    "y directo. No muestres SQL, codigo ni detalles tecnicos del modelo. Si falta "
    "informacion, haz una pregunta breve para aclarar."
)

SUMMARY_SYSTEM_PROMPT = (
    "Resume la conversacion para que otro analista pueda continuarla con memoria. "
    "Conserva objetivos del usuario, decisiones, filtros, metricas, entidades, "
    "periodos de tiempo y conclusiones importantes. No incluyas SQL, codigo ni "
    "detalles tecnicos. Maximo 150 palabras."
)


@dataclass(frozen=True)
class LLMProviderConfig:
    name: str
    default_base_url: str | None = None
    base_url_env: str | None = None


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


@dataclass(frozen=True)
class LLMChatService:
    model_name: str
    provider: str | None = None
    api_key: str | None = None
    temperature: float = 0.2
    system_prompt: str = DEFAULT_SYSTEM_PROMPT

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

        return ChatOpenAI(
            model=self.model_name,
            temperature=self.temperature,
            api_key=SecretStr(api_key),
            base_url=base_url,
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
            raise LLMGenerationError(
                "The assistant could not generate a response."
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
