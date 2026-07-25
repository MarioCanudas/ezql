from langchain_core.tools import tool
from langchain_core.runnables import RunnableConfig
from pydantic import ValidationError

from backend.services.agent.state import AgentConfiguration
from backend.services.user_database import RuntimeDatabaseError
from backend.services.sql_safety import UnsafeSQLError
from backend.services.agent.tool_results import tool_failure, tool_success


def _get_config(config: RunnableConfig) -> AgentConfiguration:
    try:
        return AgentConfiguration.model_validate(config.get("configurable", {}))
    except ValidationError as e:
        raise ValueError(f"Invalid configuration in config['configurable']: {e}")


@tool
def get_schema(config: RunnableConfig) -> dict:
    """Obtiene el esquema de todas las tablas en la base de datos actual."""
    agent_config = _get_config(config)
    return tool_success(
        "Esquema disponible para el análisis.",
        data=agent_config.database_service.get_schema_summary(
            agent_config.runtime_db_id, user_id=agent_config.user_id
        ),
    )


@tool
def preview_table(table_name: str, config: RunnableConfig, limit: int = 20) -> dict:
    """Muestra un preview de los registros de una tabla dada."""
    agent_config = _get_config(config)
    try:
        result = agent_config.database_service.preview_table(
            agent_config.runtime_db_id,
            user_id=agent_config.user_id,
            table_name=table_name,
            limit=limit,
        )
        return tool_success("Vista previa disponible.", data={
            "columns": result.columns,
            "row_count": result.row_count,
            "truncated": result.truncated,
            "rows_preview": result.rows[:5],
        })
    except Exception:
        return tool_failure("No fue posible obtener una vista previa de esa tabla.")


@tool
def count_rows(table_name: str, config: RunnableConfig) -> dict:
    """Cuenta el total de registros en una tabla."""
    agent_config = _get_config(config)
    try:
        total = agent_config.database_service.count_rows(
            agent_config.runtime_db_id, user_id=agent_config.user_id, table_name=table_name
        )
        return tool_success("Conteo disponible.", data={"total": total})
    except Exception:
        return tool_failure("No fue posible contar los registros solicitados.")


@tool
def summarize_column(table_name: str, column_name: str, config: RunnableConfig) -> dict:
    """Resume estadísticamente una columna específica de una tabla."""
    agent_config = _get_config(config)
    try:
        result = agent_config.database_service.summarize_column(
            agent_config.runtime_db_id,
            user_id=agent_config.user_id,
            table_name=table_name,
            column_name=column_name,
        )
        return tool_success("Resumen de columna disponible.", data={
            "columns": result.columns,
            "row_count": result.row_count,
            "truncated": result.truncated,
            "rows_preview": result.rows[:5],
        })
    except Exception:
        return tool_failure("No fue posible resumir esa columna.")


@tool
def execute_advanced_sql(sql: str, config: RunnableConfig) -> dict:
    """Ejecuta una consulta SQL de lectura compleja (JOINs, GROUP BY, subconsultas) y retorna los resultados. Úsala solo cuando las funciones básicas no basten."""
    agent_config = _get_config(config)
    try:
        result = agent_config.database_service.execute_readonly_query(
            agent_config.runtime_db_id, user_id=agent_config.user_id, sql=sql
        )
        return tool_success("Consulta completada.", data={
            "columns": result.columns,
            "row_count": result.row_count,
            "truncated": result.truncated,
            "rows_preview": result.rows[:10],
        })
    except UnsafeSQLError:
        return tool_failure("La consulta solicitada no es una operación de solo lectura válida.")
    except RuntimeDatabaseError:
        return tool_failure("No fue posible completar la consulta con los datos disponibles.")
    except Exception:
        return tool_failure("No fue posible completar la consulta solicitada.")


@tool
def search_similar_values(table_name: str, column_name: str, keyword: str, config: RunnableConfig) -> dict:
    """Busca valores categóricos reales en la base de datos que se parezcan a un keyword. Úsalo ANTES de armar un WHERE para evitar alucinaciones."""
    agent_config = _get_config(config)
    try:
        result = agent_config.database_service.search_similar_values(
            agent_config.runtime_db_id, user_id=agent_config.user_id, table_name=table_name, column_name=column_name, keyword=keyword
        )
        return tool_success("Valores coincidentes disponibles.", data={"matched_values": [row[column_name] for row in result.rows]})
    except Exception:
        return tool_failure("No fue posible buscar valores similares.")


@tool
def get_column_distinct_values(table_name: str, column_name: str, config: RunnableConfig) -> dict:
    """Obtiene los valores únicos (categorías) más frecuentes de una columna. Útil para conocer los valores exactos antes de un filtrado estricto."""
    agent_config = _get_config(config)
    try:
        result = agent_config.database_service.get_column_distinct_values(
            agent_config.runtime_db_id, user_id=agent_config.user_id, table_name=table_name, column_name=column_name
        )
        return tool_success("Valores frecuentes disponibles.", data={"distinct_values": [row[column_name] for row in result.rows]})
    except Exception:
        return tool_failure("No fue posible obtener los valores de esa columna.")


@tool
def validate_sql_syntax(sql: str, config: RunnableConfig) -> dict:
    """Valida la sintaxis de una consulta SQL de forma segura sin ejecutarla. Úsalo siempre antes de usar execute_advanced_sql con consultas complejas."""
    agent_config = _get_config(config)
    result = agent_config.database_service.validate_sql_syntax(
        agent_config.runtime_db_id, user_id=agent_config.user_id, sql=sql
    )
    return tool_success(result) if result == "Sintaxis válida." else tool_failure("La consulta necesita ajustes antes de ejecutarse.")


@tool
def query_planner(plan_steps: list[str]) -> dict:
    """Úsalo para escribir los pasos lógicos de cómo vas a resolver el problema (ej. uniones, filtros) ANTES de generar SQL."""
    return tool_success("Plan de consulta registrado.", data={"steps": len(plan_steps)})
