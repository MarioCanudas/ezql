from __future__ import annotations

import json
from collections.abc import Sequence
from typing import Any

from langchain_core.messages import HumanMessage, SystemMessage
from pydantic import JsonValue

from backend.models import AgentReply, Messages, QueryResult, RuntimeTable
from backend.prompts import (
    SQL_AGENT_SYSTEM_PROMPT,
    SQL_ANSWER_PROMPT,
    SQL_CLARIFY_PROMPT,
    SQL_RECOVERY_PROMPT,
    SQL_TOOL_SELECTION_PROMPT,
)
from backend.services.llm_chat_service import LLMChatService, LLMGenerationError
from backend.services.sql_safety import UnsafeSQLError
from backend.services.user_database_service import (
    RuntimeDatabaseError,
    UserDatabaseService,
)

PREVIEW_ROWS_FOR_LLM = 5
DEFAULT_PREVIEW_LIMIT = 20
MAX_TOOL_LIMIT = 100


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
            schema = self.database_service.get_schema(runtime_db_id, user_id=user_id)
        except RuntimeDatabaseError as exc:
            return AgentReply(text=str(exc))

        payload = self._select_action(
            message=message,
            history=history,
            summary=summary,
            schema=schema,
        )
        action = self._normalize_action(payload.get("action"))
        args = self._extract_args(payload)

        if action in {"clarify", "unsupported"}:
            return AgentReply(
                text=self._extract_message(
                    payload,
                    user_message=message,
                    reason="El modelo solicitó aclaración o marcó la solicitud como no soportada.",
                )
            )

        if action == "schema":
            data = self._schema_rows(schema)
            tool_result = {"tables": self._schema_payload(schema)}
            return self._answer_with_tool(
                message=message,
                tool_name="schema",
                tool_args={},
                tool_result=tool_result,
                data=data,
            )

        if action == "preview_table":
            table_name = self._extract_table_name(args)
            if not table_name:
                return AgentReply(
                    text=self._clarify_with_llm(
                        user_message=message,
                        reason="Falta el nombre de la tabla para mostrar un preview.",
                    )
                )
            limit = self._ensure_limit(args.get("limit"), default=DEFAULT_PREVIEW_LIMIT)
            result = self.database_service.preview_table(
                runtime_db_id,
                user_id=user_id,
                table_name=table_name,
                limit=limit,
            )
            return self._answer_with_tool(
                message=message,
                tool_name="preview_table",
                tool_args={"table_name": table_name, "limit": limit},
                tool_result=self._result_payload(result),
                data=result.rows,
            )

        if action == "count_rows":
            table_name = self._extract_table_name(args)
            if not table_name:
                return AgentReply(
                    text=self._clarify_with_llm(
                        user_message=message,
                        reason="Falta el nombre de la tabla para contar registros.",
                    )
                )
            total = self.database_service.count_rows(
                runtime_db_id,
                user_id=user_id,
                table_name=table_name,
            )
            return self._answer_with_tool(
                message=message,
                tool_name="count_rows",
                tool_args={"table_name": table_name},
                tool_result={"total": total},
                data=[{"total": total}],
            )

        if action == "summarize_column":
            table_name = self._extract_table_name(args)
            column_name = self._extract_column_name(args)
            if not table_name or not column_name:
                return AgentReply(
                    text=self._clarify_with_llm(
                        user_message=message,
                        reason="Falta tabla y/o columna para resumir.",
                    )
                )
            result = self.database_service.summarize_column(
                runtime_db_id,
                user_id=user_id,
                table_name=table_name,
                column_name=column_name,
            )
            return self._answer_with_tool(
                message=message,
                tool_name="summarize_column",
                tool_args={"table_name": table_name, "column_name": column_name},
                tool_result=self._result_payload(result),
                data=result.rows,
            )

        if action == "sql_query":
            sql = args.get("sql") or payload.get("sql")
            if not isinstance(sql, str) or not sql.strip():
                return AgentReply(
                    text=self._clarify_with_llm(
                        user_message=message,
                        reason="Falta la consulta SQL para resolver la pregunta.",
                    )
                )
            try:
                result = self.database_service.execute_readonly_query(
                    runtime_db_id,
                    user_id=user_id,
                    sql=sql,
                )
            except UnsafeSQLError as exc:
                return self._recover_from_unsafe_sql(
                    user_message=message,
                    reason=str(exc),
                )
            except RuntimeDatabaseError as exc:
                return AgentReply(text=str(exc))

            return self._answer_with_tool(
                message=message,
                tool_name="sql_query",
                tool_args={"sql": sql},
                tool_result=self._result_payload(result),
                data=result.rows,
            )

        return AgentReply(
            text=self._clarify_with_llm(
                user_message=message,
                reason="No se reconoció la acción seleccionada.",
            )
        )

    def _select_action(
        self,
        *,
        message: str,
        history: Sequence[Messages],
        summary: str | None,
        schema: list[RuntimeTable],
    ) -> dict[str, Any]:
        schema_context = self._schema_summary(schema)
        history_context = self._format_history(history[-8:])
        summary_context = f"Resumen del chat: {summary}" if summary else ""
        prompt = (
            f"{SQL_TOOL_SELECTION_PROMPT}\n\n"
            f"Estructura disponible:\n{schema_context}\n\n"
            f"{summary_context}\n\n"
            f"Historial reciente:\n{history_context}\n\n"
            f"Pregunta del usuario: {message}"
        )
        response_text = self._invoke_llm(prompt)
        return self._parse_json_response(response_text)

    def _answer_with_tool(
        self,
        *,
        message: str,
        tool_name: str,
        tool_args: dict[str, Any],
        tool_result: dict[str, Any],
        data: list[dict[str, JsonValue]] | None,
    ) -> AgentReply:
        prompt = (
            f"{SQL_ANSWER_PROMPT}\n\n"
            f"Pregunta del usuario: {message}\n"
            f"Herramienta usada: {tool_name}\n"
            f"Parámetros: {json.dumps(tool_args, ensure_ascii=False)}\n"
            f"Resultado (JSON): {json.dumps(tool_result, ensure_ascii=False)}"
        )
        response_text = self._invoke_llm(prompt)
        return AgentReply(text=response_text.strip(), data=data)

    def _recover_from_unsafe_sql(self, *, user_message: str, reason: str) -> AgentReply:
        prompt = (
            f"{SQL_RECOVERY_PROMPT}\n\n"
            f"Motivo: {reason}\n"
            f"Pregunta original: {user_message}"
        )
        payload = self._parse_json_response(self._invoke_llm(prompt))
        action = self._normalize_action(payload.get("action"))
        if action in {"clarify", "unsupported"}:
            message = self._extract_message(
                payload,
                user_message=user_message,
                reason="Recuperación por SQL inseguro.",
            )
            return AgentReply(text=message)

        return AgentReply(
            text=self._clarify_with_llm(
                user_message=user_message,
                reason="La consulta no es segura y no se pudo recuperar una respuesta.",
            )
        )

    def _invoke_llm(self, prompt: str) -> str:
        try:
            client = self.llm_service._build_client()
            response = client.invoke(
                [
                    SystemMessage(content=SQL_AGENT_SYSTEM_PROMPT),
                    HumanMessage(content=prompt),
                ]
            )
        except Exception as exc:
            raise LLMGenerationError(
                "The SQL assistant could not generate a response."
            ) from exc
        return (
            response.content
            if isinstance(response.content, str)
            else str(response.content)
        )

    def _parse_json_response(self, response_content: Any) -> dict[str, Any]:
        text = (
            response_content
            if isinstance(response_content, str)
            else str(response_content)
        )
        clean_text = text.strip()
        if clean_text.startswith("```"):
            clean_text = clean_text.strip("`")
            clean_text = clean_text.removeprefix("json").strip()
        try:
            value = json.loads(clean_text)
        except json.JSONDecodeError:
            first = clean_text.find("{")
            last = clean_text.rfind("}")
            if first == -1 or last == -1 or last <= first:
                return {"action": "clarify", "args": {"message": ""}}
            value = json.loads(clean_text[first : last + 1])
        if not isinstance(value, dict):
            return {"action": "clarify", "args": {"message": ""}}
        return value

    def _normalize_action(self, action: str | None) -> str:
        value = (action or "").strip().casefold()
        mapping = {
            "query": "sql_query",
            "sql": "sql_query",
            "sql_query": "sql_query",
            "schema": "schema",
            "preview": "preview_table",
            "preview_table": "preview_table",
            "count": "count_rows",
            "count_rows": "count_rows",
            "summary": "summarize_column",
            "summarize_column": "summarize_column",
            "clarify": "clarify",
            "unsupported": "unsupported",
        }
        return mapping.get(value, value or "clarify")

    def _extract_args(self, payload: dict[str, Any]) -> dict[str, Any]:
        args = payload.get("args")
        return args if isinstance(args, dict) else {}

    def _extract_message(
        self,
        payload: dict[str, Any],
        *,
        user_message: str,
        reason: str,
    ) -> str:
        args = self._extract_args(payload)
        message = payload.get("message") or args.get("message")
        if isinstance(message, str) and message.strip():
            return message.strip()
        return self._clarify_with_llm(user_message=user_message, reason=reason)

    def _extract_table_name(self, args: dict[str, Any]) -> str | None:
        for key in ("table_name", "table", "tabla"):
            value = args.get(key)
            if isinstance(value, str) and value.strip():
                return value.strip()
        return None

    def _extract_column_name(self, args: dict[str, Any]) -> str | None:
        for key in ("column_name", "column", "columna"):
            value = args.get(key)
            if isinstance(value, str) and value.strip():
                return value.strip()
        return None

    def _ensure_limit(self, value: Any, *, default: int) -> int:
        try:
            limit = int(value)
        except (TypeError, ValueError):
            return default
        return max(1, min(limit, MAX_TOOL_LIMIT))

    def _schema_summary(self, schema: list[RuntimeTable]) -> str:
        if not schema:
            return "No hay tablas disponibles en la base."
        lines = []
        for table in schema:
            columns = ", ".join(
                f"{column.name} ({column.type or 'tipo no declarado'})"
                for column in table.columns
            )
            lines.append(f"- {table.name}: {columns}")
        return "\n".join(lines)

    def _schema_payload(self, schema: list[RuntimeTable]) -> list[dict[str, Any]]:
        return [
            {
                "name": table.name,
                "columns": [column.name for column in table.columns],
            }
            for table in schema
        ]

    def _schema_rows(self, schema: list[RuntimeTable]) -> list[dict[str, JsonValue]]:
        rows: list[dict[str, JsonValue]] = []
        for table in schema:
            rows.append(
                {
                    "tabla": table.name,
                    "columnas": ", ".join(column.name for column in table.columns),
                }
            )
        return rows

    def _result_payload(self, result: QueryResult) -> dict[str, Any]:
        preview = result.rows[:PREVIEW_ROWS_FOR_LLM]
        return {
            "columns": result.columns,
            "row_count": result.row_count,
            "truncated": result.truncated,
            "rows_preview": preview,
        }

    def _clarify_with_llm(self, *, user_message: str, reason: str) -> str:
        prompt = (
            f"{SQL_CLARIFY_PROMPT}\nMotivo: {reason}\nPregunta original: {user_message}"
        )
        payload = self._parse_json_response(self._invoke_llm(prompt))
        message = self._extract_args(payload).get("message") or payload.get("message")
        if isinstance(message, str) and message.strip():
            return message.strip()
        return "Necesito un poco más de detalle para responder."

    def _format_history(self, history: Sequence[Messages]) -> str:
        if not history:
            return "Sin historial previo."
        lines = []
        for message in history:
            content = (
                message.content.get("text")
                if isinstance(message.content, dict)
                else None
            )
            if not content:
                continue
            role = "Usuario" if message.role.value == "user" else "EzQL"
            lines.append(f"{role}: {content}")
        return "\n".join(lines) or "Sin historial previo."
