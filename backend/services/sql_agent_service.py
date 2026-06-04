from __future__ import annotations

from collections.abc import Sequence

from langchain.agents import create_agent
from langchain_core.messages import HumanMessage, SystemMessage

from backend.models import AgentReply, Messages
from backend.prompts import SQL_AGENT_SYSTEM_PROMPT
from backend.services.llm_chat_service import LLMChatService, LLMGenerationError
from backend.services.tool_agent_service import ToolAgentService
from backend.services.user_database_service import (
    RuntimeDatabaseError,
    UserDatabaseService,
)


class SQLAgentService:
    def __init__(
        self,
        *,
        database_service: UserDatabaseService,
        model_name: str,
        provider: str | None,
        api_key: str,
        temperature: float = 0.0,
    ) -> None:
        self.database_service = database_service
        self.llm_service = LLMChatService(
            model_name=model_name,
            provider=provider,
            api_key=api_key,
            temperature=temperature,
            system_prompt=SQL_AGENT_SYSTEM_PROMPT,
        )
        self.tool_service = ToolAgentService(database_service=database_service)

    def generate_reply(
        self,
        *,
        user_message: str,
        history: Sequence[Messages],
        summary: str | None,
        runtime_db_id: str,
        user_id: int,
    ) -> AgentReply:
        message = user_message.strip()
        if not message:
            return AgentReply(text="Escribe una pregunta sobre tu base de datos.")

        try:
            self.database_service.get_schema(runtime_db_id, user_id=user_id)
        except RuntimeDatabaseError as exc:
            return AgentReply(text=str(exc))

        self.tool_service.set_context(runtime_db_id=runtime_db_id, user_id=user_id)
        tools = self.tool_service.build_tools()

        llm = self.llm_service._build_client()
        agent = create_agent(model=llm, tools=tools, system_prompt=SQL_AGENT_SYSTEM_PROMPT)

        chat_messages = []
        if summary:
            chat_messages.append(SystemMessage(content=f"Resumen del chat: {summary}"))
        chat_messages.extend(self.llm_service._history_messages(history))
        chat_messages.append(HumanMessage(content=message))

        try:
            response = agent.invoke(
                {"messages": chat_messages},
                config={"recursion_limit": 25},
            )
            text_response = str(response["messages"][-1].content)
        except Exception as exc:
            raise LLMGenerationError(
                "The SQL assistant could not generate a response."
            ) from exc

        return AgentReply(text=text_response, data=self.tool_service.last_query_data)

