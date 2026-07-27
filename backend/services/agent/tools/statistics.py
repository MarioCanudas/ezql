from langchain_core.runnables import RunnableConfig
from langchain_core.tools import tool
from pydantic import ValidationError

from backend.models.statistics import AnalysisScope
from backend.models.blocks import MetricBlock, TableBlock
from backend.services.agent.statistics_sandbox import DockerStatisticsSandbox
from backend.services.agent.state import AgentConfiguration
from backend.services.agent.tool_results import tool_failure, tool_success


def _get_config(config: RunnableConfig) -> AgentConfiguration:
    try:
        return AgentConfiguration.model_validate(config.get("configurable", {}))
    except ValidationError as exc:
        raise ValueError(f"Invalid configuration in config['configurable']: {exc}") from exc


@tool
def analyze_trend(
    scope: AnalysisScope, config: RunnableConfig
) -> dict:
    """Analiza una métrica agregada por día, semana, mes, trimestre o año."""
    agent_config = _get_config(config)
    try:
        result = agent_config.database_service.analyze_trend_scope_pandas(
            agent_config.runtime_db_id,
            user_id=agent_config.user_id,
            scope=scope,
        )
    except Exception:
        return tool_failure("No fue posible calcular una tendencia con los datos disponibles.")
    if "error" in result:
        return tool_failure("No fue posible calcular una tendencia con los datos disponibles.")

    return tool_success(
        result["message"],
        data=result,
        warnings=result.get("warnings", []),
    )


@tool
def detect_outliers(
    scope: AnalysisScope, config: RunnableConfig
) -> dict:
    """Detecta segmentos atípicos con el método IQR sobre una métrica agregada."""
    agent_config = _get_config(config)
    try:
        result = agent_config.database_service.detect_outliers_scope_pandas(
            agent_config.runtime_db_id,
            user_id=agent_config.user_id,
            scope=scope,
        )
    except Exception:
        return tool_failure("No fue posible evaluar anomalías con los datos disponibles.")
    if "error" in result:
        return tool_failure("No fue posible evaluar anomalías con los datos disponibles.")

    return tool_success(
        result["message"],
        data=result,
        warnings=result.get("warnings", []),
    )


@tool
def profile_data(scope: AnalysisScope, column_name: str, config: RunnableConfig) -> dict:
    """Perfila calidad, nulos, valores distintos y categorías frecuentes de una columna."""
    agent_config = _get_config(config)
    try:
        result = agent_config.database_service.profile_data_pandas(
            agent_config.runtime_db_id, user_id=agent_config.user_id, scope=scope, column_name=column_name
        )
    except Exception:
        return tool_failure("No fue posible perfilar los datos solicitados.")
    if "error" in result:
        return tool_failure("No fue posible perfilar los datos solicitados.")
    return tool_success(result["method"], data=result, warnings=result.get("warnings", []))


@tool
def describe_metric(scope: AnalysisScope, config: RunnableConfig) -> dict:
    """Calcula descriptivos, percentiles y rango intercuartílico de una métrica numérica."""
    agent_config = _get_config(config)
    try:
        result = agent_config.database_service.describe_metric_pandas(
            agent_config.runtime_db_id, user_id=agent_config.user_id, scope=scope
        )
    except Exception:
        return tool_failure("No fue posible resumir la métrica solicitada.")
    if "error" in result:
        return tool_failure("No fue posible resumir la métrica solicitada.")
    return tool_success(result["method"], data=result, warnings=result.get("warnings", []))


@tool
def compare_segments(scope: AnalysisScope, config: RunnableConfig) -> dict:
    """Compara y ordena segmentos por una métrica agregada, con participación porcentual."""
    agent_config = _get_config(config)
    try:
        result = agent_config.database_service.compare_segments_pandas(
            agent_config.runtime_db_id, user_id=agent_config.user_id, scope=scope
        )
    except Exception:
        return tool_failure("No fue posible comparar los segmentos solicitados.")
    if "error" in result:
        return tool_failure("No fue posible comparar los segmentos solicitados.")
    return tool_success(result["method"], data=result, warnings=result.get("warnings", []))


@tool
def run_statistics_python(
    code: str,
    grant_id: str,
    step_id: str,
    config: RunnableConfig,
) -> dict:
    """Ejecuta análisis descriptivo avanzado sobre un dataset efímero autorizado.

    El código recibe `data` (un DataFrame) y debe asignar `result` con `findings`,
    `metrics`, `tables` y opcionalmente `warnings`. No puede acceder a archivos,
    red ni a la base de datos.
    """
    agent_config = _get_config(config)
    resolved = agent_config.statistics_grants.resolve(
        grant_id=grant_id,
        step_id=step_id,
        user_id=agent_config.user_id,
        runtime_db_id=agent_config.runtime_db_id,
    )
    if resolved is None:
        return tool_failure("El conjunto autorizado ya no está disponible para este análisis.")
    descriptor, records = resolved
    try:
        result, duration = DockerStatisticsSandbox().execute(code=code, records=records)
    except RuntimeError:
        return tool_failure("No fue posible completar el análisis avanzado con los datos autorizados.")

    suggested_blocks = [
        MetricBlock(label=label, value=str(value)).model_dump()
        for label, value in result.metrics.items()
    ]
    for table in result.tables:
        columns = table.get("columns", [])
        rows = table.get("data", [])
        if columns and all(isinstance(row, dict) for row in rows):
            suggested_blocks.append(TableBlock(
                title=str(table.get("title", "Resultados del análisis")),
                columns=columns,
                data=rows,
            ).model_dump())
    return tool_success(
        "Análisis estadístico avanzado completado.",
        data={
            "method": "sandbox estadístico aislado",
            "findings": result.findings,
            "metrics": result.metrics,
            "tables": result.tables,
            "population": {
                "rows": descriptor.row_count,
                "columns": descriptor.columns,
                "mode": descriptor.mode,
            },
            "duration_ms": round(duration * 1000),
            "suggested_blocks": suggested_blocks,
        },
        warnings=[*descriptor.warnings, *result.warnings],
    )
