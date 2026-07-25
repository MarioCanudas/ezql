from typing import Literal

from langchain_core.runnables import RunnableConfig
from langchain_core.tools import tool
from pydantic import ValidationError

from backend.models.blocks import ChartBlock
from backend.services.agent.state import AgentConfiguration
from backend.services.agent.tool_results import tool_failure, tool_success


def _get_config(config: RunnableConfig) -> AgentConfiguration:
    try:
        return AgentConfiguration.model_validate(config.get("configurable", {}))
    except ValidationError as exc:
        raise ValueError(f"Invalid configuration in config['configurable']: {exc}") from exc


def _chart_result(
    *,
    chart_type: Literal["bar", "line", "scatter"],
    table_name: str,
    title: str,
    x_axis: str,
    y_axis: list[str],
    source_columns: list[str],
    sql: str,
    config: RunnableConfig,
) -> dict:
    agent_config = _get_config(config)
    try:
        agent_config.database_service.validate_table_columns(
            agent_config.runtime_db_id,
            user_id=agent_config.user_id,
            table_name=table_name,
            column_names=source_columns,
        )
        result = agent_config.database_service.execute_readonly_query(
            agent_config.runtime_db_id, user_id=agent_config.user_id, sql=sql
        )
    except Exception:
        return tool_failure("No fue posible preparar la visualización solicitada.")
    if not result.rows:
        return tool_failure("No hay datos suficientes para crear esta visualización.")

    block = ChartBlock(
        chart_type=chart_type,
        title=title,
        x_axis=x_axis,
        y_axis=y_axis,
        data=result.rows,
    ).model_dump()
    warnings = ["La visualización usa una muestra limitada de filas."] if result.truncated else []
    return tool_success(
        f"Visualización '{title}' preparada.",
        data={"row_count": result.row_count, "truncated": result.truncated},
        warnings=warnings,
        blocks=[block],
    )


@tool
def create_bar_chart(
    table_name: str,
    category_column: str,
    value_column: str,
    title: str,
    config: RunnableConfig,
    limit: int = 20,
) -> dict:
    """Crea una gráfica de barras agrupada por categoría."""
    safe_limit = max(1, min(limit, 100))
    sql = (
        f'SELECT "{category_column}", SUM("{value_column}") AS total '
        f'FROM "{table_name}" GROUP BY "{category_column}" '
        f"ORDER BY total DESC LIMIT {safe_limit}"
    )
    return _chart_result(
        chart_type="bar", table_name=table_name, title=title,
        x_axis=category_column, y_axis=["total"], source_columns=[category_column, value_column], sql=sql, config=config,
    )


@tool
def create_line_chart(
    table_name: str,
    x_column: str,
    y_column: str,
    title: str,
    config: RunnableConfig,
    limit: int = 100,
) -> dict:
    """Crea una gráfica de líneas ordenada por su eje X."""
    safe_limit = max(1, min(limit, 100))
    sql = (
        f'SELECT "{x_column}", "{y_column}" FROM "{table_name}" '
        f'WHERE "{x_column}" IS NOT NULL AND "{y_column}" IS NOT NULL '
        f'ORDER BY "{x_column}" LIMIT {safe_limit}'
    )
    return _chart_result(
        chart_type="line", table_name=table_name, title=title,
        x_axis=x_column, y_axis=[y_column], source_columns=[x_column, y_column], sql=sql, config=config,
    )


@tool
def create_scatter_chart(
    table_name: str,
    x_column: str,
    y_column: str,
    title: str,
    config: RunnableConfig,
    limit: int = 100,
) -> dict:
    """Crea una gráfica de dispersión con pares numéricos no nulos."""
    safe_limit = max(1, min(limit, 100))
    sql = (
        f'SELECT "{x_column}", "{y_column}" FROM "{table_name}" '
        f'WHERE "{x_column}" IS NOT NULL AND "{y_column}" IS NOT NULL '
        f"LIMIT {safe_limit}"
    )
    return _chart_result(
        chart_type="scatter", table_name=table_name, title=title,
        x_axis=x_column, y_axis=[y_column], source_columns=[x_column, y_column], sql=sql, config=config,
    )
