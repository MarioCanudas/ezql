from typing import Annotated, Literal, Any
from pydantic import BaseModel, Field

class TableBlock(BaseModel):
    type: Literal["table"] = "table"
    rows: list[dict[str, Any]]

class MetricBlock(BaseModel):
    type: Literal["metric"] = "metric"
    label: str
    value: Any

class TrendBlock(BaseModel):
    type: Literal["trend"] = "trend"
    metric: str
    pct_change: float | None
    direction: str

class OutlierBlock(BaseModel):
    type: Literal["outliers"] = "outliers"
    message: str

class ChartBlock(BaseModel):
    type: Literal["chart"] = "chart"
    spec: dict[str, Any]

DataBlock = Annotated[
    TableBlock | MetricBlock | TrendBlock | OutlierBlock | ChartBlock,
    Field(discriminator="type")
]

# Flexible block that allows unstructured data to ensure backward compatibility
# with historical chats stored in the database.
FlexibleDataBlock = DataBlock | list[Any] | dict[str, Any]
