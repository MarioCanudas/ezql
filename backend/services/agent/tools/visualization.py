from langchain_core.tools import tool
from langchain_core.runnables import RunnableConfig
from pydantic import ValidationError

from backend.services.agent.state import AgentConfiguration


def _get_config(config: RunnableConfig) -> AgentConfiguration:
    try:
        return AgentConfiguration.model_validate(config.get("configurable", {}))
    except ValidationError as e:
        raise ValueError(f"Invalid configuration in config['configurable']: {e}")


@tool
def create_bar_chart(
    table_name: str,
    category_column: str,
    value_column: str,
    title: str,
    config: RunnableConfig,
    limit: int = 20,
) -> dict | str:
    """Crea una gráfica de barras agrupando por una columna categórica y sumando
    una métrica. Útil para comparaciones como 'ventas por categoría', 'usuarios
    por país', etc."""
    agent_config = _get_config(config)
    try:
        import altair as alt
        import pandas as pd

        sql = (
            f'SELECT "{category_column}", SUM("{value_column}") as total '
            f'FROM "{table_name}" '
            f'GROUP BY "{category_column}" '
            f"ORDER BY total DESC LIMIT {int(limit)}"
        )
        result = agent_config.database_service.execute_readonly_query(
            agent_config.runtime_db_id, user_id=agent_config.user_id, sql=sql
        )

        df = pd.DataFrame(result.rows)
        if df.empty:
            return "No hay datos para graficar."

        chart = (
            alt.Chart(df)
            .mark_bar()
            .encode(
                x=alt.X("total:Q", title=value_column),
                y=alt.Y(f"{category_column}:N", sort="-x", title=category_column),
                tooltip=[category_column, "total"],
            )
            .properties(title=title)
        )

        spec = chart.to_dict()
        query_data_ref = config.get("configurable", {}).get("query_data_ref")
        if query_data_ref is not None:
            from backend.models.blocks import ChartBlock

            query_data_ref.append(ChartBlock(spec=spec).model_dump())

        return {"status": "chart_created", "title": title, "data_points": len(df)}
    except Exception as e:
        return f"Error creando gráfica de barras: {e}"


@tool
def create_line_chart(
    table_name: str,
    x_column: str,
    y_column: str,
    title: str,
    config: RunnableConfig,
    limit: int = 100,
) -> dict | str:
    """Crea una gráfica de líneas para mostrar evolución temporal o secuencial.
    Útil para tendencias como 'ventas por mes', 'registros por día', etc."""
    agent_config = _get_config(config)
    try:
        import altair as alt
        import pandas as pd

        sql = (
            f'SELECT "{x_column}", "{y_column}" '
            f'FROM "{table_name}" '
            f'ORDER BY "{x_column}" LIMIT {int(limit)}'
        )
        result = agent_config.database_service.execute_readonly_query(
            agent_config.runtime_db_id, user_id=agent_config.user_id, sql=sql
        )

        df = pd.DataFrame(result.rows)
        if df.empty:
            return "No hay datos para graficar."

        chart = (
            alt.Chart(df)
            .mark_line(point=True)
            .encode(
                x=alt.X(f"{x_column}:N", title=x_column),
                y=alt.Y(f"{y_column}:Q", title=y_column),
                tooltip=[x_column, y_column],
            )
            .properties(title=title)
        )

        spec = chart.to_dict()
        query_data_ref = config.get("configurable", {}).get("query_data_ref")
        if query_data_ref is not None:
            from backend.models.blocks import ChartBlock

            query_data_ref.append(ChartBlock(spec=spec).model_dump())

        return {"status": "chart_created", "title": title, "data_points": len(df)}
    except Exception as e:
        return f"Error creando gráfica de líneas: {e}"
