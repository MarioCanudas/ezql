import sqlite3

import pytest

from backend.models.statistics import AnalysisFilter, AnalysisScope
from backend.services.user_database import UserDatabase


@pytest.fixture(name="statistics_database")
def fixture_statistics_database(tmp_path):
    path = tmp_path / "statistics.db"
    connection = sqlite3.connect(path)
    connection.execute("CREATE TABLE sales (day TEXT, region TEXT, amount REAL, status TEXT)")
    connection.executemany(
        "INSERT INTO sales VALUES (?, ?, ?, ?)",
        [
            ("2025-01-02", "North", 10, "won"), ("2025-01-10", "North", 20, "won"),
            ("2025-02-03", "North", 30, "lost"), ("2025-02-12", "South", 20, None),
            ("2025-03-01", "South", 40, "won"), ("2025-03-11", "East", 50, "won"),
            ("2025-04-01", "East", 60, "lost"), ("2025-04-10", "West", 500, "won"),
        ],
    )
    connection.commit()
    connection.close()
    database = UserDatabase()
    runtime = database.register_uploaded_sqlite(user_id=1, display_name="stats", filename="statistics.db", content=path.read_bytes())
    yield database, runtime.id
    database.close()


def test_profile_and_describe_metric_return_exact_foundations(statistics_database):
    database, runtime_id = statistics_database
    scope = AnalysisScope(table_name="sales", metric_column="amount")
    profile = database.profile_data_pandas(runtime_id, user_id=1, scope=scope, column_name="status")
    assert profile["population"]["missing_rows"] == 1
    assert profile["distinct_values"] == 2
    assert profile["suggested_blocks"]

    described = database.describe_metric_pandas(runtime_id, user_id=1, scope=scope)
    assert described["statistics"]["mean"] == pytest.approx(91.25)
    assert described["statistics"]["median"] == pytest.approx(35.0)
    assert described["statistics"]["iqr"] == pytest.approx(32.5)


def test_filters_ranking_and_aggregated_trend(statistics_database):
    database, runtime_id = statistics_database
    filtered = AnalysisScope(table_name="sales", dimension_column="region", metric_column="amount", aggregation="sum", filters=[AnalysisFilter(column="status", operator="eq", value="won")])
    comparison = database.compare_segments_pandas(runtime_id, user_id=1, scope=filtered)
    assert comparison["leader"]["region"] == "West"
    assert comparison["leader"]["value"] == 500.0

    trend = database.analyze_trend_scope_pandas(runtime_id, user_id=1, scope=AnalysisScope(table_name="sales", time_column="day", metric_column="amount", aggregation="sum", time_granularity="month"))
    assert [period["value"] for period in trend["periods"]] == [30.0, 50.0, 90.0, 560.0]
    assert trend["direction"] == "up"


def test_iqr_outliers_and_safe_small_sample(statistics_database):
    database, runtime_id = statistics_database
    scope = AnalysisScope(table_name="sales", dimension_column="region", metric_column="amount", aggregation="sum")
    result = database.detect_outliers_scope_pandas(runtime_id, user_id=1, scope=scope)
    assert result["method"].startswith("IQR")
    assert result["outliers"]
    assert result["outliers"][0]["region"] == "West"

    small = database.detect_outliers_scope_pandas(runtime_id, user_id=1, scope=AnalysisScope(table_name="sales", dimension_column="status", aggregation="count"))
    assert "error" in small
