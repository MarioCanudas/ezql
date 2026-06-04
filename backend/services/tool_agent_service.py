from __future__ import annotations

import inspect
from typing import Any, Callable

from langchain_core.tools import BaseTool, tool
from pydantic import JsonValue

from backend.services.sql_safety import UnsafeSQLError
from backend.services.user_database_service import (
    RuntimeDatabaseError,
    UserDatabaseService,
)


def register_tool(func: Callable[..., Any]) -> Callable[..., Any]:
    """Decorador para marcar un método como herramienta (tool) del agente."""
    setattr(func, "_is_agent_tool", True)
    return func


class ToolAgentService:
    def __init__(self, *, database_service: UserDatabaseService) -> None:
        self.database_service = database_service
        self.runtime_db_id: str | None = None
        self.user_id: int | None = None
        self.last_query_data: list[dict[str, JsonValue]] | None = None

    def set_context(self, *, runtime_db_id: str, user_id: int) -> None:
        """Establece el contexto de la base de datos y usuario para la petición actual."""
        self.runtime_db_id = runtime_db_id
        self.user_id = user_id
        self.last_query_data = None

    @register_tool
    def get_schema(self) -> str:
        """Obtiene el esquema de todas las tablas en la base de datos actual."""
        if self.runtime_db_id is None or self.user_id is None:
            return "Error: Database context not initialized."
        return self.database_service.get_schema_summary(
            self.runtime_db_id, user_id=self.user_id
        )

    @register_tool
    def preview_table(self, table_name: str, limit: int = 20) -> dict | str:
        """Muestra un preview de los registros de una tabla dada."""
        if self.runtime_db_id is None or self.user_id is None:
            return "Error: Database context not initialized."
        try:
            result = self.database_service.preview_table(
                self.runtime_db_id, user_id=self.user_id, table_name=table_name, limit=limit
            )
            self.last_query_data = result.rows
            return {
                "columns": result.columns,
                "row_count": result.row_count,
                "truncated": result.truncated,
                "rows_preview": result.rows[:5],
            }
        except Exception as e:
            return f"Error: {e}"

    @register_tool
    def count_rows(self, table_name: str) -> dict | str:
        """Cuenta el total de registros en una tabla."""
        if self.runtime_db_id is None or self.user_id is None:
            return "Error: Database context not initialized."
        try:
            total = self.database_service.count_rows(
                self.runtime_db_id, user_id=self.user_id, table_name=table_name
            )
            self.last_query_data = [{"total": total}]
            return {"total": total}
        except Exception as e:
            return f"Error: {e}"

    @register_tool
    def summarize_column(self, table_name: str, column_name: str) -> dict | str:
        """Resume estadísticamente una columna específica de una tabla."""
        if self.runtime_db_id is None or self.user_id is None:
            return "Error: Database context not initialized."
        try:
            result = self.database_service.summarize_column(
                self.runtime_db_id,
                user_id=self.user_id,
                table_name=table_name,
                column_name=column_name,
            )
            self.last_query_data = result.rows
            return {
                "columns": result.columns,
                "row_count": result.row_count,
                "truncated": result.truncated,
                "rows_preview": result.rows[:5],
            }
        except Exception as e:
            return f"Error: {e}"

    @register_tool
    def execute_advanced_sql(self, sql: str) -> dict | str:
        """Ejecuta una consulta SQL de lectura compleja (JOINs, GROUP BY, subconsultas) y retorna los resultados. Úsala solo cuando las funciones básicas no basten."""
        if self.runtime_db_id is None or self.user_id is None:
            return "Error: Database context not initialized."
        try:
            result = self.database_service.execute_readonly_query(
                self.runtime_db_id, user_id=self.user_id, sql=sql
            )
            self.last_query_data = result.rows
            return {
                "columns": result.columns,
                "row_count": result.row_count,
                "truncated": result.truncated,
                "rows_preview": result.rows[:5],
            }
        except UnsafeSQLError as e:
            return f"Consulta insegura: {e}. Solo puedes hacer consultas SELECT de solo lectura."
        except RuntimeDatabaseError as e:
            return f"Error de SQLite: {e}. Revisa el esquema, las comillas y la sintaxis."
        except Exception as e:
            return f"Error desconocido: {e}"

    def build_tools(self) -> list[BaseTool]:
        """Busca todas las funciones etiquetadas como tools y las envuelve en langchain tool."""
        tools: list[BaseTool] = []
        for _, member in inspect.getmembers(self, predicate=inspect.ismethod):
            if getattr(member, "_is_agent_tool", False):
                tools.append(tool(member))
        return tools
