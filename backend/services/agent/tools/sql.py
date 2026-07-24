from langchain_core.tools import tool
from langchain_core.runnables import RunnableConfig
from pydantic import ValidationError

from backend.services.agent.state import AgentConfiguration
from backend.services.user_database import RuntimeDatabaseError
from backend.services.sql_safety import UnsafeSQLError
from backend.models.blocks import TableBlock, MetricBlock

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
        query_data_ref = config.get("configurable", {}).get("query_data_ref")
        if query_data_ref is not None:
            query_data_ref.append(TableBlock(rows=result.rows).model_dump())
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
        query_data_ref = config.get("configurable", {}).get("query_data_ref")
        if query_data_ref is not None:
            query_data_ref.append(MetricBlock(label="Total de Filas", value=total).model_dump())
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
        query_data_ref = config.get("configurable", {}).get("query_data_ref")
        if query_data_ref is not None:
            query_data_ref.append(TableBlock(rows=result.rows).model_dump())
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
        query_data_ref = config.get("configurable", {}).get("query_data_ref")
        if query_data_ref is not None:
            query_data_ref.append(TableBlock(rows=result.rows).model_dump())
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

@tool
def search_similar_values(table_name: str, column_name: str, keyword: str, config: RunnableConfig) -> dict | str:
    """Busca valores categóricos reales en la base de datos que se parezcan a un keyword. Úsalo ANTES de armar un WHERE para evitar alucinaciones."""
    agent_config = _get_config(config)
    try:
        result = agent_config.database_service.search_similar_values(
            agent_config.runtime_db_id, user_id=agent_config.user_id, table_name=table_name, column_name=column_name, keyword=keyword
        )
        return {"matched_values": [row[column_name] for row in result.rows]}
    except Exception as e:
        return f"Error: {e}"

@tool
def get_column_distinct_values(table_name: str, column_name: str, config: RunnableConfig) -> dict | str:
    """Obtiene los valores únicos (categorías) más frecuentes de una columna. Útil para conocer los valores exactos antes de un filtrado estricto."""
    agent_config = _get_config(config)
    try:
        result = agent_config.database_service.get_column_distinct_values(
            agent_config.runtime_db_id, user_id=agent_config.user_id, table_name=table_name, column_name=column_name
        )
        return {"distinct_values": [row[column_name] for row in result.rows]}
    except Exception as e:
        return f"Error: {e}"

@tool
def validate_sql_syntax(sql: str, config: RunnableConfig) -> str:
    """Valida la sintaxis de una consulta SQL de forma segura sin ejecutarla. Úsalo siempre antes de usar execute_advanced_sql con consultas complejas."""
    agent_config = _get_config(config)
    return agent_config.database_service.validate_sql_syntax(
        agent_config.runtime_db_id, user_id=agent_config.user_id, sql=sql
    )

@tool
def query_planner(plan_steps: list[str]) -> str:
    """Úsalo para escribir los pasos lógicos de cómo vas a resolver el problema (ej. uniones, filtros) ANTES de generar SQL."""
    return f"Plan registrado. Pasos: {len(plan_steps)}. Procede a escribir o ejecutar el SQL."

