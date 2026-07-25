from backend.services.agent.agent_chat import AgentChat
from backend.services.agent.tools.statistics import analyze_trend, detect_outliers
from backend.services.agent.tools.visualization import create_bar_chart
from backend.services.user_database import UserDatabase


def _tool_config(database: UserDatabase, runtime_db_id: str) -> dict:
    return {
        "configurable": {
            "database_service": database,
            "llm_service": AgentChat(model_name="gpt-4o-mini", api_key="test-key"),
            "runtime_db_id": runtime_db_id,
            "user_id": 1,
        }
    }


def test_trend_tool_returns_renderable_trend_block():
    database = UserDatabase()
    try:
        runtime = database.register_sample_sqlite(user_id=1)
        result = analyze_trend.invoke(
            {
                "table_name": "netflix_titles",
                "date_column": "release_year",
                "metric_column": "release_year",
            },
            config=_tool_config(database, runtime.id),
        )
        assert result["ok"] is True
        assert result["blocks"][0]["type"] == "trend"
        assert result["blocks"][0]["direction"] in {"up", "down", "stable"}
    finally:
        database.close()


def test_statistics_tools_return_safe_failure_for_invalid_columns():
    database = UserDatabase()
    try:
        runtime = database.register_sample_sqlite(user_id=1)
        result = detect_outliers.invoke(
            {
                "table_name": "netflix_titles",
                "category_column": "missing_column",
                "metric_column": "release_year",
            },
            config=_tool_config(database, runtime.id),
        )
        assert result == {"ok": False, "summary": "No fue posible evaluar anomalías con los datos disponibles.", "data": None, "warnings": [], "blocks": []}
    finally:
        database.close()


def test_chart_tool_returns_a_valid_chart_block():
    database = UserDatabase()
    try:
        runtime = database.register_sample_sqlite(user_id=1)
        result = create_bar_chart.invoke(
            {
                "table_name": "netflix_titles",
                "category_column": "type",
                "value_column": "release_year",
                "title": "Títulos por tipo",
            },
            config=_tool_config(database, runtime.id),
        )
        assert result["ok"] is True
        assert result["blocks"][0]["type"] == "chart"
        assert result["blocks"][0]["x_axis"] == "type"
    finally:
        database.close()
