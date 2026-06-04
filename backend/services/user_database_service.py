from __future__ import annotations

import shutil
import sqlite3
import tempfile
import uuid
from datetime import datetime
from pathlib import Path

from pydantic import JsonValue

from backend.models import (
    QueryResult,
    RuntimeColumn,
    RuntimeDatabaseInternal,
    RuntimeDatabaseRead,
    RuntimeTable,
)
from backend.services.sql_safety import limit_readonly_sql, quote_identifier

MAX_UPLOAD_BYTES = 50 * 1024 * 1024
MAX_ROWS = 100
MAX_COLUMNS = 50
MAX_CELL_CHARS = 500
_ALLOWED_EXTENSIONS = {".db", ".sqlite", ".sqlite3"}


class RuntimeDatabaseError(RuntimeError):
    pass


class RuntimeDatabaseNotFoundError(RuntimeDatabaseError):
    pass


class UserDatabaseService:
    def __init__(self, *, temp_root: Path | None = None) -> None:
        self._temp_root = temp_root or Path(tempfile.mkdtemp(prefix="ezql_uploads_"))
        self._temp_root.mkdir(parents=True, exist_ok=True)
        self._databases: dict[str, RuntimeDatabaseInternal] = {}
        self._sample_path = (
            Path(__file__).resolve().parents[2]
            / "frontend"
            / "test_data"
            / "netflix.db"
        )

    def close(self) -> None:
        for database in list(self._databases.values()):
            if database.delete_on_close:
                database.path.unlink(missing_ok=True)
        self._databases.clear()
        if self._temp_root.exists():
            shutil.rmtree(self._temp_root, ignore_errors=True)

    def register_sample_sqlite(
        self,
        *,
        user_id: int,
        runtime_id: str | None = None,
    ) -> RuntimeDatabaseRead:
        if not self._sample_path.exists():
            raise RuntimeDatabaseError("La base de prueba no está disponible.")

        database = RuntimeDatabaseInternal(
            id=runtime_id or f"sample-{user_id}",
            user_id=user_id,
            name="Base de prueba Netflix",
            path=self._sample_path,
            source="sample",
            created_at=datetime.now(),
            delete_on_close=False,
        )
        self._validate_sqlite_file(database.path)
        self._databases[database.id] = database
        return self._to_read(database)

    def register_uploaded_sqlite(
        self,
        *,
        user_id: int,
        display_name: str,
        filename: str,
        content: bytes,
        runtime_id: str | None = None,
    ) -> RuntimeDatabaseRead:
        suffix = Path(filename).suffix.casefold()
        if suffix not in _ALLOWED_EXTENSIONS:
            raise RuntimeDatabaseError(
                "Solo se aceptan archivos SQLite .db, .sqlite o .sqlite3."
            )
        if not content:
            raise RuntimeDatabaseError("El archivo está vacío.")
        if len(content) > MAX_UPLOAD_BYTES:
            raise RuntimeDatabaseError(
                "El archivo supera el tamaño máximo permitido de 50 MB."
            )

        runtime_id = runtime_id or str(uuid.uuid4())
        path = self._temp_root / f"{runtime_id}{suffix}"
        path.write_bytes(content)

        try:
            self._validate_sqlite_file(path)
        except Exception:
            path.unlink(missing_ok=True)
            raise

        database = RuntimeDatabaseInternal(
            id=runtime_id,
            user_id=user_id,
            name=display_name.strip() or Path(filename).stem or "Base SQLite",
            path=path,
            source="upload",
            created_at=datetime.now(),
            delete_on_close=True,
        )
        self._databases[database.id] = database
        return self._to_read(database)

    def list_databases(
        self, *, user_id: int | None = None
    ) -> list[RuntimeDatabaseRead]:
        databases = self._databases.values()
        if user_id is not None:
            databases = [
                database for database in databases if database.user_id == user_id
            ]
        return [self._to_read(database) for database in databases]

    def remove_database(self, database_id: str, *, user_id: int) -> None:
        database = self.get_database(database_id, user_id=user_id)
        if database.delete_on_close:
            database.path.unlink(missing_ok=True)
        self._databases.pop(database_id, None)

    def get_database(
        self, database_id: str, *, user_id: int | None = None
    ) -> RuntimeDatabaseInternal:
        database = self._databases.get(database_id)
        if database is None:
            raise RuntimeDatabaseNotFoundError(
                "La base de datos temporal ya no está cargada. Vuelve a subirla para continuar."
            )
        if user_id is not None and database.user_id != user_id:
            raise RuntimeDatabaseNotFoundError(
                "No se encontró la base de datos temporal."
            )
        return database

    def get_schema(
        self, database_id: str, *, user_id: int | None = None
    ) -> list[RuntimeTable]:
        database = self.get_database(database_id, user_id=user_id)
        return self._read_schema(database.path)

    def get_schema_summary(
        self, database_id: str, *, user_id: int | None = None
    ) -> str:
        tables = self.get_schema(database_id, user_id=user_id)
        if not tables:
            return "La base no contiene tablas disponibles para analizar."

        lines = []
        for table in tables:
            columns = ", ".join(
                f"{column.name} ({column.type or 'tipo no declarado'})"
                for column in table.columns
            )
            lines.append(f"- {table.name}: {columns}")
        return "Tablas disponibles:\n" + "\n".join(lines)

    def preview_table(
        self,
        database_id: str,
        *,
        user_id: int,
        table_name: str,
        limit: int = 20,
    ) -> QueryResult:
        safe_limit = max(1, min(limit, MAX_ROWS))
        sql = f"SELECT * FROM {quote_identifier(table_name)}"
        return self.execute_readonly_query(
            database_id,
            user_id=user_id,
            sql=sql,
            max_rows=safe_limit,
        )

    def count_rows(self, database_id: str, *, user_id: int, table_name: str) -> int:
        sql = f"SELECT COUNT(*) AS total FROM {quote_identifier(table_name)}"
        result = self.execute_readonly_query(
            database_id,
            user_id=user_id,
            sql=sql,
            max_rows=1,
        )
        if not result.rows:
            return 0
        value = result.rows[0].get("total")
        if isinstance(value, bool):
            return int(value)
        if isinstance(value, int | float | str):
            return int(value)
        return 0

    def summarize_column(
        self,
        database_id: str,
        *,
        user_id: int,
        table_name: str,
        column_name: str,
    ) -> QueryResult:
        schema = self.get_schema(database_id, user_id=user_id)
        table = next((item for item in schema if item.name == table_name), None)
        column = (
            None
            if table is None
            else next(
                (item for item in table.columns if item.name == column_name), None
            )
        )
        declared_type = (column.type or "").casefold() if column else ""
        quoted_table = quote_identifier(table_name)
        quoted_column = quote_identifier(column_name)
        is_numeric = any(
            marker in declared_type
            for marker in ("int", "real", "numeric", "decimal", "double", "float")
        )

        if is_numeric:
            sql = (
                "SELECT "
                f"COUNT({quoted_column}) AS valores, "
                f"SUM(CASE WHEN {quoted_column} IS NULL THEN 1 ELSE 0 END) AS nulos, "
                f"MIN({quoted_column}) AS minimo, "
                f"MAX({quoted_column}) AS maximo, "
                f"AVG({quoted_column}) AS promedio "
                f"FROM {quoted_table}"
            )
            return self.execute_readonly_query(
                database_id,
                user_id=user_id,
                sql=sql,
                max_rows=1,
            )

        sql = (
            "SELECT "
            f"{quoted_column} AS valor, "
            "COUNT(*) AS frecuencia "
            f"FROM {quoted_table} "
            f"WHERE {quoted_column} IS NOT NULL "
            f"GROUP BY {quoted_column} "
            "ORDER BY frecuencia DESC "
            "LIMIT 10"
        )
        return self.execute_readonly_query(
            database_id,
            user_id=user_id,
            sql=sql,
            max_rows=10,
        )

    def execute_readonly_query(
        self,
        database_id: str,
        *,
        user_id: int,
        sql: str,
        max_rows: int = MAX_ROWS,
    ) -> QueryResult:
        database = self.get_database(database_id, user_id=user_id)
        safe_limit = max(1, min(max_rows, MAX_ROWS))
        limited_sql = limit_readonly_sql(sql, max_rows=safe_limit + 1)

        try:
            with self._connect_readonly(database.path) as connection:
                cursor = connection.execute(limited_sql)
                raw_columns = [
                    description[0] for description in cursor.description or []
                ]
                selected_columns = raw_columns[:MAX_COLUMNS]
                rows = cursor.fetchall()
        except sqlite3.Error as exc:
            raise RuntimeDatabaseError(
                "No pude completar la consulta con la estructura actual de la base."
            ) from exc

        truncated = len(rows) > safe_limit
        rows = rows[:safe_limit]
        formatted_rows: list[dict[str, JsonValue]] = []
        for row in rows:
            formatted_rows.append(
                {
                    column: self._to_json_value(row[column])
                    for column in selected_columns
                    if column in row.keys()
                }
            )

        return QueryResult(
            columns=selected_columns,
            rows=formatted_rows,
            row_count=len(formatted_rows),
            truncated=truncated,
        )

    def _to_read(self, database: RuntimeDatabaseInternal) -> RuntimeDatabaseRead:
        return RuntimeDatabaseRead(
            id=database.id,
            user_id=database.user_id,
            name=database.name,
            source=database.source,
            created_at=database.created_at,
            tables=self._read_schema(database.path),
        )

    def _validate_sqlite_file(self, path: Path) -> None:
        try:
            with self._connect_readonly(path) as connection:
                integrity = connection.execute("PRAGMA integrity_check").fetchone()
                if integrity is None or integrity[0] != "ok":
                    raise RuntimeDatabaseError(
                        "El archivo SQLite no superó la validación."
                    )
                table_count = connection.execute(
                    "SELECT COUNT(*) FROM sqlite_master "
                    "WHERE type IN ('table', 'view') AND name NOT LIKE 'sqlite_%'"
                ).fetchone()[0]
                if int(table_count) == 0:
                    raise RuntimeDatabaseError(
                        "La base no contiene tablas para analizar."
                    )
        except sqlite3.Error as exc:
            raise RuntimeDatabaseError(
                "El archivo no parece ser una base SQLite válida."
            ) from exc

    def _read_schema(self, path: Path) -> list[RuntimeTable]:
        try:
            with self._connect_readonly(path) as connection:
                table_rows = connection.execute(
                    "SELECT name FROM sqlite_master "
                    "WHERE type IN ('table', 'view') AND name NOT LIKE 'sqlite_%' "
                    "ORDER BY name"
                ).fetchall()
                tables: list[RuntimeTable] = []
                for table_row in table_rows:
                    table_name = str(table_row["name"])
                    column_rows = connection.execute(
                        f"PRAGMA table_info({quote_identifier(table_name)})"
                    ).fetchall()
                    columns = [
                        RuntimeColumn(
                            name=str(column_row["name"]),
                            type=str(column_row["type"] or "") or None,
                            nullable=not bool(column_row["notnull"]),
                            primary_key=bool(column_row["pk"]),
                        )
                        for column_row in column_rows
                    ]
                    tables.append(RuntimeTable(name=table_name, columns=columns))
                return tables
        except sqlite3.Error as exc:
            raise RuntimeDatabaseError(
                "No pude leer la estructura de la base."
            ) from exc

    def _connect_readonly(self, path: Path) -> sqlite3.Connection:
        connection = sqlite3.connect(
            f"file:{path}?mode=ro",
            uri=True,
            timeout=5.0,
        )
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA query_only = ON")
        return connection

    def _to_json_value(self, value: object) -> JsonValue:
        if value is None or isinstance(value, bool | int | float):
            return value
        if isinstance(value, bytes):
            return "<datos binarios>"
        text = str(value)
        if len(text) > MAX_CELL_CHARS:
            return text[:MAX_CELL_CHARS] + "…"
        return text
