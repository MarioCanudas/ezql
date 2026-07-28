from __future__ import annotations

from langchain_core.runnables import RunnableConfig
from langchain_core.tools import tool
from pydantic import ValidationError

from backend.models.blocks import MetricBlock, TableBlock
from backend.services.agent.state import AgentConfiguration
from backend.services.agent.tool_results import tool_failure, tool_success


def _get_config(config: RunnableConfig) -> AgentConfiguration:
    try:
        return AgentConfiguration.model_validate(config.get("configurable", {}))
    except ValidationError as exc:
        raise ValueError(f"Invalid configuration in config['configurable']: {exc}") from exc


@tool
def assess_data_quality(
    table_name: str,
    columns: list[str],
    config: RunnableConfig,
) -> dict:
    """Evalúa cobertura, nulos, cardinalidad y duplicados de columnas reales.

    No devuelve filas de la tabla. Solo produce métricas y una tabla resumida
    aptas para la respuesta de negocio.
    """

    agent_config = _get_config(config)
    if not columns:
        return tool_failure("Selecciona al menos una columna para evaluar la calidad.")
    try:
        agent_config.database_service.validate_table_columns(
            agent_config.runtime_db_id,
            user_id=agent_config.user_id,
            table_name=table_name,
            column_names=columns,
        )
        quoted = [f'"{column.replace(chr(34), chr(34) * 2)}"' for column in columns]
        expressions = ["COUNT(*) AS total_rows"]
        for index, column in enumerate(quoted):
            expressions.extend([
                f"SUM(CASE WHEN {column} IS NULL THEN 1 ELSE 0 END) AS null_{index}",
                f"COUNT(DISTINCT {column}) AS distinct_{index}",
            ])
        escaped_table = table_name.replace(chr(34), chr(34) * 2)
        sql = f'SELECT {", ".join(expressions)} FROM "{escaped_table}"'
        result = agent_config.database_service.execute_readonly_query(
            agent_config.runtime_db_id,
            user_id=agent_config.user_id,
            sql=sql,
        )
    except Exception:
        return tool_failure("No fue posible evaluar la calidad de los datos disponibles.")

    row = result.rows[0] if result.rows else {}
    total_rows = int(row.get("total_rows") or 0)
    schema = agent_config.database_service.get_schema(
        agent_config.runtime_db_id,
        user_id=agent_config.user_id,
    )
    table = next((item for item in schema if item.name == table_name), None)
    declared_types = {
        column.name: column.type or "tipo no declarado"
        for column in (table.columns if table else [])
        if column.name in columns
    }
    quality_rows: list[dict[str, object]] = []
    for index, column in enumerate(columns):
        nulls = int(row.get(f"null_{index}") or 0)
        distinct = int(row.get(f"distinct_{index}") or 0)
        observed_types: dict[str, int] = {}
        try:
            type_result = agent_config.database_service.execute_readonly_query(
                agent_config.runtime_db_id,
                user_id=agent_config.user_id,
                sql=(
                    f'SELECT typeof({quoted[index]}) AS observed_type, COUNT(*) AS count '
                    f'FROM "{escaped_table}" GROUP BY typeof({quoted[index]})'
                ),
            )
            observed_types = {
                str(item.get("observed_type") or "null"): int(item.get("count") or 0)
                for item in type_result.rows
            }
        except Exception:
            # Declared schema types remain useful if observed-type inspection is
            # unavailable in a compatible read-only database implementation.
            observed_types = {}
        non_null_types = {key: value for key, value in observed_types.items() if key != "null"}
        quality_rows.append({
            "columna": column,
            "nulos": nulls,
            "porcentaje_nulos": round((nulls / total_rows) * 100, 2) if total_rows else 0,
            "valores_distintos": distinct,
            "tipo_declarado": declared_types.get(column, "tipo no declarado"),
            "tipos_observados": ", ".join(sorted(non_null_types)) or "sin valores",
        })

    duplicate_rows = 0
    try:
        duplicate_sql = (
            "SELECT COALESCE(SUM(group_count - 1), 0) AS duplicate_rows "
            "FROM (SELECT COUNT(*) AS group_count "
            f'FROM "{escaped_table}" GROUP BY {", ".join(quoted)} '
            "HAVING COUNT(*) > 1)"
        )
        duplicate_result = agent_config.database_service.execute_readonly_query(
            agent_config.runtime_db_id,
            user_id=agent_config.user_id,
            sql=duplicate_sql,
        )
        if duplicate_result.rows:
            duplicate_rows = int(duplicate_result.rows[0].get("duplicate_rows") or 0)
    except Exception:
        # Duplicate analysis is advisory; preserve the reliable null/cardinality
        # results if a dialect-specific grouping operation is unavailable.
        pass

    suggested_blocks = [
        MetricBlock(label="Filas evaluadas", value=f"{total_rows:,}").model_dump(),
        MetricBlock(label="Filas duplicadas estimadas", value=f"{duplicate_rows:,}").model_dump(),
        TableBlock(
            title="Calidad por columna",
            columns=[
                "columna",
                "nulos",
                "porcentaje_nulos",
                "valores_distintos",
                "tipo_declarado",
                "tipos_observados",
            ],
            data=quality_rows,
        ).model_dump(),
    ]
    warnings = [
        f"La columna {item['columna']} contiene valores nulos."
        for item in quality_rows
        if item["nulos"]
    ]
    warnings.extend(
        f"La columna {item['columna']} contiene tipos observados mixtos."
        for item in quality_rows
        if "," in str(item["tipos_observados"])
    )
    if total_rows == 0:
        warnings.append("La tabla no contiene filas; la calidad no puede representarse todavía.")
    elif total_rows < 30:
        warnings.append("La evaluación usa una población pequeña y debe interpretarse con cautela.")
    return tool_success(
        "Evaluación de calidad completada.",
        data={
            "table_name": table_name,
            "population": {"rows": total_rows, "columns": columns},
            "findings": quality_rows,
            "duplicate_rows": duplicate_rows,
            "declared_types": declared_types,
            "suggested_blocks": suggested_blocks,
        },
        warnings=warnings,
    )


quality_tools = [assess_data_quality]
