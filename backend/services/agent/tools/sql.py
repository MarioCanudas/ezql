from langchain_core.tools import tool
from langchain_core.runnables import RunnableConfig
from pydantic import ValidationError

from backend.services.agent.state import AgentConfiguration
from backend.services.user_database import RuntimeDatabaseError
from backend.services.sql_safety import UnsafeSQLError

def _get_config(config: RunnableConfig) -> AgentConfiguration:
    try:
        return AgentConfiguration.model_validate(config.get("configurable", {}))
    except ValidationError as e:
        raise ValueError(f"Invalid configuration in config['configurable']: {e}")

@tool
def get_schema(config: RunnableConfig) -> str:
    """Obtiene el esquema de todas las tablas en la base de datos actual."""
    agent_config = _get_config(config)
    return agent_config.database_service.get_schema_summary(
        agent_config.runtime_db_id, user_id=agent_config.user_id
    )

@tool
def preview_table(table_name: str, config: RunnableConfig, limit: int = 20) -> dict | str:
    """Muestra un preview de los registros de una tabla dada."""
    agent_config = _get_config(config)
    try:
        result = agent_config.database_service.preview_table(
            agent_config.runtime_db_id,
            user_id=agent_config.user_id,
            table_name=table_name,
            limit=limit,
        )
        agent_config.query_data.append(result.rows)
        return {
            "columns": result.columns,
            "row_count": result.row_count,
            "truncated": result.truncated,
            "rows_preview": result.rows[:5],
        }
    except Exception as e:
        return f"Error: {e}"

@tool
def count_rows(table_name: str, config: RunnableConfig) -> dict | str:
    """Cuenta el total de registros en una tabla."""
    agent_config = _get_config(config)
    try:
        total = agent_config.database_service.count_rows(
            agent_config.runtime_db_id, user_id=agent_config.user_id, table_name=table_name
        )
        agent_config.query_data.append([{"total": total}])
        return {"total": total}
    except Exception as e:
        return f"Error: {e}"

@tool
def summarize_column(table_name: str, column_name: str, config: RunnableConfig) -> dict | str:
    """Resume estadísticamente una columna específica de una tabla."""
    agent_config = _get_config(config)
    try:
        result = agent_config.database_service.summarize_column(
            agent_config.runtime_db_id,
            user_id=agent_config.user_id,
            table_name=table_name,
            column_name=column_name,
        )
        agent_config.query_data.append(result.rows)
        return {
            "columns": result.columns,
            "row_count": result.row_count,
            "truncated": result.truncated,
            "rows_preview": result.rows[:5],
        }
    except Exception as e:
        return f"Error: {e}"

@tool
def execute_advanced_sql(sql: str, config: RunnableConfig) -> dict | str:
    """Ejecuta una consulta SQL de lectura compleja (JOINs, GROUP BY, subconsultas) y retorna los resultados. Úsala solo cuando las funciones básicas no basten."""
    agent_config = _get_config(config)
    try:
        result = agent_config.database_service.execute_readonly_query(
            agent_config.runtime_db_id, user_id=agent_config.user_id, sql=sql
        )
        agent_config.query_data.append(result.rows)
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
