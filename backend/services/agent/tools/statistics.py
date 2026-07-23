from langchain_core.tools import tool
from langchain_core.runnables import RunnableConfig
from langgraph.types import Command
from pydantic import ValidationError

from backend.services.agent.state import AgentConfiguration
from backend.models.blocks import TrendBlock, OutlierBlock, TableBlock


def _get_config(config: RunnableConfig) -> AgentConfiguration:
    try:
        return AgentConfiguration.model_validate(config.get("configurable", {}))
    except ValidationError as e:
        raise ValueError(f"Invalid configuration in config['configurable']: {e}")


@tool
def analyze_trend(
    table_name: str, date_column: str, metric_column: str, config: RunnableConfig
) -> dict | str:
    """Analiza la tendencia temporal de una métrica. Retorna la dirección (alza/baja) y el cambio promedio.
    Útil cuando el usuario pregunta por el crecimiento, comportamiento a través del tiempo o tendencias de ventas/registros.
    """
    agent_config = _get_config(config)
    try:
        result = agent_config.database_service.analyze_trend_pandas(
            agent_config.runtime_db_id,
            user_id=agent_config.user_id,
            table_name=table_name,
            date_column=date_column,
            metric_column=metric_column,
        )
        query_data_ref = config.get("configurable", {}).get("query_data_ref")
        if query_data_ref is not None:
            # Inject insight to frontend payload
            query_data_ref.append(
                TrendBlock(
                    metric=result["metric_column"],
                    pct_change=result.get("pct_change"),
                    direction=result.get("trend", "flat")
                ).model_dump()
            )
        return result
    except Exception as e:
        return f"Error en análisis de tendencia: {e}"


@tool
def detect_outliers(
    table_name: str, category_column: str, metric_column: str, config: RunnableConfig
) -> dict | str:
    """Detecta anomalías o valores atípicos (outliers) en una métrica agrupada por categorías usando Z-score.
    Útil para responder preguntas como '¿Hay algún dato raro?', '¿Qué producto vendió anormalmente más/menos?'.
    """
    agent_config = _get_config(config)
    try:
        result = agent_config.database_service.detect_outliers_pandas(
            agent_config.runtime_db_id,
            user_id=agent_config.user_id,
            table_name=table_name,
            category_column=category_column,
            metric_column=metric_column,
        )
        query_data_ref = config.get("configurable", {}).get("query_data_ref")
        if query_data_ref is not None:
            if "outliers" in result:
                query_data_ref.append(TableBlock(rows=result["outliers"]).model_dump())
            else:
                query_data_ref.append(OutlierBlock(message="Sin anomalías detectadas").model_dump())
        return result
    except Exception as e:
        return f"Error en detección de anomalías: {e}"


@tool
def transfer_to_sql() -> Command:
    """Úsalo cuando el usuario haga una pregunta que solo requiera SQL simple (ej. 'cuántos usuarios hay', 'muéstrame la tabla') o si terminaste de analizar las tendencias y le pasas el control de vuelta al Agente SQL."""
    return Command(goto="sql")
