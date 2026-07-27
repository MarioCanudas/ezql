import sqlite3

import pytest

from backend.models.statistics import StatisticsDatasetRequest
from backend.services.agent.sandbox.runner import UnsafeCode, validate_code
from backend.services.agent.statistics_grants import StatisticsGrantStore
from backend.services.user_database import UserDatabase


@pytest.fixture(name="sandbox_database")
def fixture_sandbox_database(tmp_path):
    path = tmp_path / "sandbox.db"
    connection = sqlite3.connect(path)
    connection.execute("CREATE TABLE sales (region TEXT, amount REAL, status TEXT)")
    connection.executemany(
        "INSERT INTO sales VALUES (?, ?, ?)",
        [("North", 10, "won"), ("South", 20, "won"), ("West", 30, "lost")],
    )
    connection.commit()
    connection.close()
    database = UserDatabase()
    runtime = database.register_uploaded_sqlite(
        user_id=1, display_name="sandbox", filename="sandbox.db", content=path.read_bytes()
    )
    yield database, runtime.id
    database.close()


def test_materialized_grant_is_bounded_and_bound_to_its_owner(sandbox_database):
    database, runtime_id = sandbox_database
    store = StatisticsGrantStore()
    descriptor = store.create(
        database_service=database,
        runtime_db_id=runtime_id,
        user_id=1,
        step_id="statistics-1",
        request=StatisticsDatasetRequest.model_validate({
            "mode": "rows",
            "scope": {"table_name": "sales", "filters": [{"column": "status", "value": "won"}]},
            "columns": ["region", "amount"],
        }),
    )
    resolved = store.resolve(grant_id=descriptor.grant_id, step_id="statistics-1", user_id=1, runtime_db_id=runtime_id)
    assert resolved is not None
    assert resolved[0].columns == ["region", "amount"]
    assert resolved[1] == [{"region": "North", "amount": 10.0}, {"region": "South", "amount": 20.0}]
    assert store.resolve(grant_id=descriptor.grant_id, step_id="statistics-1", user_id=2, runtime_db_id=runtime_id) is None


def test_aggregate_grant_exposes_only_grouped_values(sandbox_database):
    database, runtime_id = sandbox_database
    records, columns, _ = database.materialize_statistics_dataset(
        runtime_id,
        user_id=1,
        request=StatisticsDatasetRequest.model_validate({
            "mode": "aggregates",
            "scope": {"table_name": "sales", "dimension_column": "region", "metric_column": "amount", "aggregation": "sum"},
            "columns": ["region"],
        }),
    )
    assert columns == ["region", "value"]
    assert records[0] == {"region": "West", "value": 30.0}


@pytest.mark.parametrize("code", [
    "open('/tmp/nope')",
    "import os\nresult = {}",
    "result = data.__class__",
    "data.to_csv('/tmp/export.csv')",
])
def test_runner_rejects_file_and_runtime_escape_attempts(code):
    with pytest.raises(UnsafeCode):
        validate_code(code)


def test_runner_accepts_simple_descriptive_program():
    validate_code("result = {'metrics': {'rows': len(data), 'mean': float(data['amount'].mean())}}")
