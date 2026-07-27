from backend.services.agent.agent_chat import AgentChat
from backend.services.agent.tools.statistics import describe_metric, detect_outliers
from backend.services.agent.tools.visualization import create_bar_chart, create_line_chart
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


def test_describe_metric_tool_returns_evidence_with_validated_suggested_blocks():
    database = UserDatabase()
    try:
        runtime = database.register_sample_sqlite(user_id=1)
        result = describe_metric.invoke(
            {
                "scope": {
                    "table_name": "netflix_titles",
                    "metric_column": "release_year",
                },
            },
            config=_tool_config(database, runtime.id),
        )
        assert result["ok"] is True
        assert result["data"]["statistics"]["mean"] > 0
        assert result["data"]["suggested_blocks"]
    finally:
        database.close()


def test_statistics_tools_return_safe_failure_for_invalid_columns():
    database = UserDatabase()
    try:
        runtime = database.register_sample_sqlite(user_id=1)
        result = detect_outliers.invoke(
            {
                "scope": {
                    "table_name": "netflix_titles",
                    "dimension_column": "missing_column",
                    "metric_column": "release_year",
                    "aggregation": "mean",
                },
            },
            config=_tool_config(database, runtime.id),
        )
        assert result == {"ok": False, "summary": "No fue posible evaluar anomalías con los datos disponibles.", "data": None, "warnings": []}
    finally:
        database.close()


def test_chart_tool_returns_chart_evidence_without_ui_block():
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
        assert result["data"]["chart"]["chart_type"] == "bar"
        assert result["data"]["chart"]["x_axis"] == "type"
    finally:
        database.close()


def test_line_chart_aggregates_movie_duration_by_decade():
    database = UserDatabase()
    try:
        runtime = database.register_sample_sqlite(user_id=1)
        result = create_line_chart.invoke(
            {
                "table_name": "netflix_titles",
                "x_column": "release_year",
                "y_column": "duration",
                "title": "Duración promedio de películas por década",
                "aggregation": "average",
                "bucket_size": 10,
                "numeric_prefix": True,
                "filter_column": "type",
                "filter_value": "Movie",
            },
            config=_tool_config(database, runtime.id),
        )

        assert result["ok"] is True
        chart = result["data"]["chart"]
        assert chart["chart_type"] == "line"
        assert chart["x_axis"] == "release_year (bloques de 10)"
        assert chart["y_axis"] == ["average_duration"]
        assert chart["data"]
        assert all("average_duration" in row for row in chart["data"])
    finally:
        database.close()
