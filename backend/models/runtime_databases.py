from datetime import datetime
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, ConfigDict, JsonValue


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


class RuntimeDatabaseInternal(BaseModel):
    model_config = ConfigDict(frozen=True)

    id: str
    user_id: int
    name: str
    path: Path
    source: Literal["upload", "sample"]
    created_at: datetime
    delete_on_close: bool = False


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
