from typing import Literal

from langchain_core.runnables import RunnableConfig
from langchain_core.tools import tool
from pydantic import ValidationError

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

    warnings = ["La visualización usa una muestra limitada de filas."] if result.truncated else []
    return tool_success(
        f"Visualización '{title}' preparada.",
        data={
            "row_count": result.row_count,
            "truncated": result.truncated,
            "chart": {
                "chart_type": chart_type,
                "title": title,
                "x_axis": x_axis,
                "y_axis": y_axis,
                "data": result.rows,
            },
        },
        warnings=warnings,
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
    aggregation: Literal["none", "average", "sum", "count"] = "none",
    bucket_size: int | None = None,
    numeric_prefix: bool = False,
    filter_column: str | None = None,
    filter_value: str | None = None,
) -> dict:
    """Crea una gráfica de líneas; permite agregación, décadas y filtros simples."""
    safe_limit = max(1, min(limit, 100))
    if filter_column and filter_value is None:
        return tool_failure("Para filtrar la visualización se requiere un valor de filtro.")
    if bucket_size is not None and not 1 <= bucket_size <= 100:
        return tool_failure("El tamaño del período para la visualización no es válido.")

    source_columns = [x_column, y_column] + ([filter_column] if filter_column else [])
    x_expression = f'"{x_column}"'
    x_label = x_column
    if bucket_size:
        x_expression = f'(CAST("{x_column}" AS INTEGER) / {bucket_size}) * {bucket_size}'
        x_label = f"{x_column} (bloques de {bucket_size})"

    numeric_expression = f'"{y_column}"'
    if numeric_prefix:
        numeric_expression = f'CAST(SUBSTR("{y_column}", 1, INSTR("{y_column}", " ") - 1) AS REAL)'
    where_parts = [f'"{x_column}" IS NOT NULL', f'"{y_column}" IS NOT NULL']
    if filter_column:
        escaped_value = (filter_value or "").replace("'", "''")
        where_parts.append(f'"{filter_column}" = \'{escaped_value}\'')
    where_clause = " AND ".join(where_parts)

    if aggregation == "none":
        metric_expression = numeric_expression
        metric_label = y_column
        grouping = ""
    else:
        aggregate_name = {"average": "AVG", "sum": "SUM", "count": "COUNT"}[aggregation]
        aggregate_value = "*" if aggregation == "count" else numeric_expression
        metric_label = f"{aggregation}_{y_column}" if aggregation != "count" else "count"
        metric_expression = f"{aggregate_name}({aggregate_value})"
        grouping = f" GROUP BY {x_expression}"
    sql = (
        f"SELECT {x_expression} AS \"{x_label}\", {metric_expression} AS \"{metric_label}\" "
        f'FROM "{table_name}" WHERE {where_clause}{grouping} '
        f'ORDER BY "{x_label}" LIMIT {safe_limit}'
    )
    return _chart_result(
        chart_type="line", table_name=table_name, title=title,
        x_axis=x_label, y_axis=[metric_label], source_columns=source_columns, sql=sql, config=config,
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
