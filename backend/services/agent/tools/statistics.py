from langchain_core.runnables import RunnableConfig
from langchain_core.tools import tool
from pydantic import ValidationError

from backend.models.blocks import OutlierBlock, TrendBlock
from backend.services.agent.state import AgentConfiguration
from backend.services.agent.tool_results import tool_failure, tool_success


def _get_config(config: RunnableConfig) -> AgentConfiguration:
    try:
        return AgentConfiguration.model_validate(config.get("configurable", {}))
    except ValidationError as exc:
        raise ValueError(f"Invalid configuration in config['configurable']: {exc}") from exc


@tool
def analyze_trend(
    table_name: str, date_column: str, metric_column: str, config: RunnableConfig
) -> dict:
    """Analiza una tendencia temporal y genera un bloque de tendencia listo para presentar."""
    agent_config = _get_config(config)
    try:
        result = agent_config.database_service.analyze_trend_pandas(
            agent_config.runtime_db_id,
            user_id=agent_config.user_id,
            table_name=table_name,
            date_column=date_column,
            metric_column=metric_column,
        )
    except Exception:
        return tool_failure("No fue posible calcular una tendencia con los datos disponibles.")
    if "error" in result:
        return tool_failure("No fue posible calcular una tendencia con los datos disponibles.")

    block = TrendBlock(
        metric=result["metric"],
        pct_change=result.get("pct_change"),
        direction=result["direction"],
    ).model_dump()
    return tool_success(
        result["message"],
        data=result,
        warnings=result.get("warnings", []),
        blocks=[block],
    )


@tool
def detect_outliers(
    table_name: str, category_column: str, metric_column: str, config: RunnableConfig
) -> dict:
    """Detecta anomalías en una métrica y devuelve un bloque de alerta presentable."""
    agent_config = _get_config(config)
    try:
        result = agent_config.database_service.detect_outliers_pandas(
            agent_config.runtime_db_id,
            user_id=agent_config.user_id,
            table_name=table_name,
            category_column=category_column,
            metric_column=metric_column,
        )
    except Exception:
        return tool_failure("No fue posible evaluar anomalías con los datos disponibles.")
    if "error" in result:
        return tool_failure("No fue posible evaluar anomalías con los datos disponibles.")

    return tool_success(
        result["message"],
        data=result,
        warnings=result.get("warnings", []),
        blocks=[OutlierBlock(message=result["message"]).model_dump()],
    )
