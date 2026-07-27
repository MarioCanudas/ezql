from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field, model_validator


FilterOperator = Literal["eq", "ne", "gt", "gte", "lt", "lte", "in", "not_in", "is_null", "not_null"]
Aggregation = Literal["count", "sum", "mean", "min", "max"]
TimeGranularity = Literal["day", "week", "month", "quarter", "year"]
DatasetGrantMode = Literal["rows", "aggregates"]


class AnalysisFilter(BaseModel):
    """A safe, structured predicate for statistical analysis."""

    column: str = Field(min_length=1)
    operator: FilterOperator = "eq"
    value: Any = None

    @model_validator(mode="after")
    def validate_value(self) -> "AnalysisFilter":
        if self.operator in {"is_null", "not_null"}:
            return self
        if self.operator in {"in", "not_in"} and (not isinstance(self.value, list) or not self.value):
            raise ValueError("Los filtros in/not_in requieren una lista no vacía.")
        if self.operator not in {"in", "not_in"} and self.value is None:
            raise ValueError("El filtro requiere un valor.")
        return self


class AnalysisScope(BaseModel):
    """Reusable, SQL-free definition of the population to analyze."""

    table_name: str = Field(min_length=1)
    filters: list[AnalysisFilter] = Field(default_factory=list, max_length=10)
    metric_column: str | None = None
    aggregation: Aggregation = "count"
    dimension_column: str | None = None
    time_column: str | None = None
    time_granularity: TimeGranularity = "month"


class StatisticsDatasetRequest(BaseModel):
    """A deliberately narrow, SQL-free request for a statistics sandbox snapshot."""

    mode: DatasetGrantMode = "rows"
    scope: AnalysisScope
    columns: list[str] = Field(min_length=1, max_length=12)
    max_rows: int = Field(default=1_000, ge=1, le=1_000)


class DatasetGrantDescriptor(BaseModel):
    """Safe grant metadata. The materialized records never live in graph state."""

    grant_id: str
    step_id: str
    mode: DatasetGrantMode
    columns: list[str]
    row_count: int
    truncated: bool = False
    warnings: list[str] = Field(default_factory=list)
    sample: list[dict[str, Any]] = Field(default_factory=list, max_length=5)
