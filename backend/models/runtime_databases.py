from datetime import datetime
from typing import Literal

from pydantic import BaseModel, JsonValue


class RuntimeColumn(BaseModel):
    name: str
    type: str | None = None
    nullable: bool = True
    primary_key: bool = False


class RuntimeTable(BaseModel):
    name: str
    columns: list[RuntimeColumn]


class RuntimeDatabaseRead(BaseModel):
    id: str
    user_id: int
    name: str
    source: Literal["upload", "sample"]
    is_temporary: bool = True
    created_at: datetime
    tables: list[RuntimeTable] = []


class RuntimeDatabaseSchema(BaseModel):
    id: str
    name: str
    tables: list[RuntimeTable]
    summary: str


class QueryResult(BaseModel):
    columns: list[str]
    rows: list[dict[str, JsonValue]]
    row_count: int
    truncated: bool = False
