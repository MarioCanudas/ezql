from __future__ import annotations

import shutil
import sqlite3
import tempfile
import uuid
from datetime import datetime
from pathlib import Path
from typing import Any, cast

from pydantic import JsonValue

from backend.models import (
    QueryResult,
    RuntimeColumn,
    RuntimeDatabaseInternal,
    RuntimeDatabaseRead,
    RuntimeTable,
)
from backend.models.blocks import MarkdownBlock, MetricBlock, TableBlock
from backend.models.statistics import AnalysisScope, StatisticsDatasetRequest
from backend.services.sql_safety import limit_readonly_sql, quote_identifier

MAX_UPLOAD_BYTES = 50 * 1024 * 1024
MAX_ROWS = 100
MAX_ANALYTIC_ROWS = 1_000
MAX_COLUMNS = 50
MAX_CELL_CHARS = 500
_ALLOWED_EXTENSIONS = {".db", ".sqlite", ".sqlite3"}
_SAMPLE_DATABASES = {
    "netflix": {
        "id_prefix": "sample-",
        "filename": "netflix.db",
        "name": "Base de prueba Netflix",
    },
    "uber": {
        "id_prefix": "sample-uber-",
        "filename": "uber_ride_bookings.db",
        "name": "Base de prueba Uber Ride Analytics",
    },
}


class RuntimeDatabaseError(RuntimeError):
    pass


class RuntimeDatabaseNotFoundError(RuntimeDatabaseError):
    pass


class UserDatabase:
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
        sample_name: str = "netflix",
    ) -> RuntimeDatabaseRead:
        sample = _SAMPLE_DATABASES.get(sample_name)
        if sample is None:
            raise RuntimeDatabaseError("La base de prueba solicitada no está disponible.")
        sample_path = self._sample_path.with_name(sample["filename"])
        if not sample_path.exists():
            raise RuntimeDatabaseError("La base de prueba no está disponible.")

        database_id = runtime_id or f"{sample['id_prefix']}{user_id}"

        database = RuntimeDatabaseInternal(
            id=database_id,
            user_id=user_id,
            name=sample["name"],
            path=sample_path,
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
        if database is None and database_id.startswith("sample-") and user_id is not None:
            sample_name = "uber" if database_id.startswith("sample-uber-") else "netflix"
            self.register_sample_sqlite(
                user_id=user_id,
                runtime_id=database_id,
                sample_name=sample_name,
            )
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
            table_info = f"- {table.name}:\n  Columnas: {columns}"

            try:
                sql = f"SELECT * FROM {quote_identifier(table.name)} LIMIT 2"
                # If user_id is None, we pass 0 or maybe just get_database directly
                database = self.get_database(database_id, user_id=user_id)
                with self._connect_readonly(database.path) as conn:
                    # Foreign keys
                    fk_rows = conn.execute(
                        f"PRAGMA foreign_key_list({quote_identifier(table.name)})"
                    ).fetchall()
                    if fk_rows:
                        fks = []
                        for fk in fk_rows:
                            fks.append(f"({fk['from']}) -> {fk['table']}({fk['to']})")
                        table_info += "\n  Foreign Keys: " + ", ".join(fks)

                    # Sample rows
                    cursor = conn.execute(sql)
                    raw_columns = [desc[0] for desc in cursor.description or []]
                    rows = cursor.fetchall()
                    if rows:
                        samples = []
                        for row in rows:
                            row_dict = {
                                col: self._to_json_value(row[col])
                                for col in raw_columns
                                if col in row.keys()
                            }
                            samples.append(str(row_dict))
                        table_info += (
                            "\n  Muestra de datos (2 filas):\n    "
                            + "\n    ".join(samples)
                        )
            except Exception:
                pass

            lines.append(table_info)
        return (
            "Esquema de la base de datos (con muestras y foreign keys):\n\n"
            + "\n\n".join(lines)
        )

    def validate_table_columns(
        self,
        database_id: str,
        *,
        user_id: int,
        table_name: str,
        column_names: list[str],
    ) -> None:
        """Reject unknown identifiers before quoted SQLite identifiers become literals."""
        table = next(
            (item for item in self.get_schema(database_id, user_id=user_id) if item.name == table_name),
            None,
        )
        if table is None:
            raise RuntimeDatabaseError("La tabla solicitada no está disponible.")
        available = {column.name for column in table.columns}
        if any(column not in available for column in column_names):
            raise RuntimeDatabaseError("Una de las columnas solicitadas no está disponible.")

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

    def search_similar_values(
        self, database_id: str, *, user_id: int, table_name: str, column_name: str, keyword: str
    ) -> QueryResult:
        # Sanitize keyword to avoid breaking the LIKE statement
        safe_keyword = keyword.replace("'", "").replace("%", "")
        sql = f"SELECT DISTINCT {quote_identifier(column_name)} FROM {quote_identifier(table_name)} WHERE {quote_identifier(column_name)} LIKE '%{safe_keyword}%' LIMIT 5"
        return self.execute_readonly_query(database_id, user_id=user_id, sql=sql, max_rows=5)

    def get_column_distinct_values(
        self, database_id: str, *, user_id: int, table_name: str, column_name: str
    ) -> QueryResult:
        sql = f"SELECT {quote_identifier(column_name)}, COUNT(*) as count FROM {quote_identifier(table_name)} GROUP BY {quote_identifier(column_name)} ORDER BY count DESC LIMIT 10"
        return self.execute_readonly_query(database_id, user_id=user_id, sql=sql, max_rows=10)

    def validate_sql_syntax(self, database_id: str, *, user_id: int, sql: str) -> str:
        database = self.get_database(database_id, user_id=user_id)
        try:
            with self._connect_readonly(database.path) as connection:
                connection.execute("EXPLAIN " + sql)
            return "Sintaxis válida."
        except sqlite3.Error as exc:
            return f"Error de sintaxis o esquema: {exc}"
            
    def _scope_where(self, database_id: str, *, user_id: int, scope: AnalysisScope) -> tuple[str, list[object]]:
        columns = [item.column for item in scope.filters]
        self.validate_table_columns(database_id, user_id=user_id, table_name=scope.table_name, column_names=columns)
        clauses: list[str] = []
        params: list[object] = []
        operations = {"eq": "=", "ne": "!=", "gt": ">", "gte": ">=", "lt": "<", "lte": "<="}
        for item in scope.filters:
            column = quote_identifier(item.column)
            if item.operator == "is_null":
                clauses.append(f"{column} IS NULL")
            elif item.operator == "not_null":
                clauses.append(f"{column} IS NOT NULL")
            elif item.operator in {"in", "not_in"}:
                values = item.value
                placeholders = ", ".join("?" for _ in values)
                clauses.append(f"{column} {'NOT IN' if item.operator == 'not_in' else 'IN'} ({placeholders})")
                params.extend(values)
            else:
                clauses.append(f"{column} {operations[item.operator]} ?")
                params.append(item.value)
        return (" WHERE " + " AND ".join(clauses)) if clauses else "", params

    def _scope_frame(
        self, database_id: str, *, user_id: int, scope: AnalysisScope, columns: list[str]
    ) -> tuple[Any, bool]:
        import pandas as pd
        self.validate_table_columns(database_id, user_id=user_id, table_name=scope.table_name, column_names=columns)
        where, params = self._scope_where(database_id, user_id=user_id, scope=scope)
        selected = ", ".join(quote_identifier(column) for column in columns)
        sql = f"SELECT {selected} FROM {quote_identifier(scope.table_name)}{where} LIMIT {MAX_ANALYTIC_ROWS + 1}"
        database = self.get_database(database_id, user_id=user_id)
        with self._connect_readonly(database.path) as connection:
            frame: Any = pd.read_sql_query(sql, connection, params=params)
        truncated = len(frame) > MAX_ANALYTIC_ROWS
        return frame.iloc[:MAX_ANALYTIC_ROWS].copy(), truncated

    def materialize_statistics_dataset(
        self,
        database_id: str,
        *,
        user_id: int,
        request: StatisticsDatasetRequest,
    ) -> tuple[list[dict], list[str], bool]:
        """Return a bounded, JSON-safe snapshot for the isolated statistics runtime."""
        scope = request.scope
        required: list[str] = list(dict.fromkeys([
            *request.columns,
            *(item.column for item in scope.filters),
            *([scope.dimension_column] if scope.dimension_column else []),
            *([scope.metric_column] if scope.metric_column else []),
        ]))
        self.validate_table_columns(
            database_id, user_id=user_id, table_name=scope.table_name, column_names=required
        )
        where, params = self._scope_where(database_id, user_id=user_id, scope=scope)
        database = self.get_database(database_id, user_id=user_id)
        limit = min(request.max_rows, MAX_ANALYTIC_ROWS)

        if request.mode == "rows":
            selected = ", ".join(quote_identifier(column) for column in request.columns)
            sql = f"SELECT {selected} FROM {quote_identifier(scope.table_name)}{where} LIMIT {limit + 1}"
        else:
            if scope.aggregation != "count" and scope.metric_column is None:
                raise RuntimeDatabaseError("La agregación solicitada requiere una métrica.")
            aggregate_name = {"mean": "AVG"}.get(scope.aggregation, scope.aggregation.upper())
            aggregate = "COUNT(*)" if scope.aggregation == "count" else (
                f"{aggregate_name}({quote_identifier(scope.metric_column or '')})"
            )
            if scope.dimension_column:
                dimension = quote_identifier(scope.dimension_column)
                sql = (
                    f"SELECT {dimension} AS {dimension}, {aggregate} AS value "
                    f"FROM {quote_identifier(scope.table_name)}{where} "
                    f"GROUP BY {dimension} ORDER BY value DESC LIMIT {limit + 1}"
                )
            else:
                sql = f"SELECT {aggregate} AS value FROM {quote_identifier(scope.table_name)}{where}"

        try:
            with self._connect_readonly(database.path) as connection:
                cursor = connection.execute(sql, params)
                columns = [description[0] for description in cursor.description or []]
                rows = cursor.fetchall()
        except sqlite3.Error as exc:
            raise RuntimeDatabaseError("No fue posible preparar los datos para el análisis.") from exc

        truncated = len(rows) > limit
        snapshot = [
            {column: self._to_json_value(row[column]) for column in columns if column in row.keys()}
            for row in rows[:limit]
        ]
        return snapshot, columns, truncated

    @staticmethod
    def _warnings(truncated: bool) -> list[str]:
        return ["El análisis se calculó sobre una muestra limitada de 1,000 filas."] if truncated else []

    def profile_data_pandas(self, database_id: str, *, user_id: int, scope: AnalysisScope, column_name: str | None = None) -> dict:
        import pandas as pd
        target = column_name or scope.metric_column
        if target is None:
            return {"error": "Indica una columna para perfilar."}
        frame, truncated = self._scope_frame(database_id, user_id=user_id, scope=scope, columns=[target])
        series: Any = frame[target]
        non_null: Any = series.dropna()
        numeric: Any = pd.to_numeric(non_null, errors="coerce")
        inferred = "numeric" if not non_null.empty and numeric.notna().mean() >= 0.9 else "categorical"
        top_values = non_null.astype(str).value_counts().head(10).rename_axis(target).reset_index(name="count").to_dict("records")
        data = {"population": {"rows": len(frame), "valid_rows": int(non_null.size), "missing_rows": int(series.isna().sum()), "truncated": truncated}, "column": target, "inferred_type": inferred, "distinct_values": int(non_null.nunique()), "top_values": top_values, "method": "perfilado descriptivo", "warnings": self._warnings(truncated)}
        data["suggested_blocks"] = [MetricBlock(label="Registros válidos", value=str(data["population"]["valid_rows"])).model_dump(), MetricBlock(label="Valores faltantes", value=str(data["population"]["missing_rows"])).model_dump(), TableBlock(title=f"Valores frecuentes de {target}", columns=[target, "count"], data=top_values).model_dump()]
        return data

    def describe_metric_pandas(self, database_id: str, *, user_id: int, scope: AnalysisScope) -> dict:
        import pandas as pd
        if scope.metric_column is None:
            return {"error": "Indica la métrica a describir."}
        frame, truncated = self._scope_frame(database_id, user_id=user_id, scope=scope, columns=[scope.metric_column])
        raw: Any = frame[scope.metric_column]
        numeric_values: Any = pd.to_numeric(raw, errors="coerce")
        values: Any = numeric_values.dropna()
        if values.empty:
            return {"error": "La métrica no contiene valores numéricos válidos."}
        q1, median, q3 = (float(cast(Any, values.quantile(q))) for q in (0.25, 0.5, 0.75))
        stats = {"min": float(values.min()), "max": float(values.max()), "mean": float(values.mean()), "median": median, "std_dev": float(values.std(ddof=1)) if len(values) > 1 else 0.0, "p25": q1, "p75": q3, "iqr": q3 - q1}
        raw_missing: Any = pd.isna(raw)
        numeric_missing: Any = pd.isna(numeric_values)
        data = {"population": {"rows": len(frame), "valid_rows": len(values), "missing_rows": int(raw_missing.sum() + (numeric_missing.sum() - raw_missing.sum())), "truncated": truncated}, "metric": scope.metric_column, "statistics": stats, "method": "estadística descriptiva", "warnings": self._warnings(truncated)}
        data["suggested_blocks"] = [MetricBlock(label=f"Media de {scope.metric_column}", value=f"{stats['mean']:,.2f}").model_dump(), MetricBlock(label="Mediana", value=f"{median:,.2f}").model_dump(), MetricBlock(label="Rango intercuartílico", value=f"{stats['iqr']:,.2f}").model_dump()]
        return data

    def compare_segments_pandas(self, database_id: str, *, user_id: int, scope: AnalysisScope) -> dict:
        import pandas as pd
        if scope.dimension_column is None:
            return {"error": "Indica una dimensión para comparar segmentos."}
        columns = [scope.dimension_column] + ([scope.metric_column] if scope.metric_column else [])
        frame, truncated = self._scope_frame(database_id, user_id=user_id, scope=scope, columns=columns)
        dimension = scope.dimension_column
        frame = frame.dropna(subset=[dimension])
        if scope.aggregation == "count":
            grouped = frame.groupby(dimension).size().rename("value")
        else:
            if scope.metric_column is None:
                return {"error": "La agregación seleccionada requiere una métrica."}
            numeric = pd.to_numeric(frame[scope.metric_column], errors="coerce")
            frame = frame.assign(_metric=numeric).dropna(subset=["_metric"])
            grouped = getattr(frame.groupby(dimension)["_metric"], {"sum": "sum", "mean": "mean", "min": "min", "max": "max"}[scope.aggregation])().rename("value")
        if grouped.empty:
            return {"error": "No hay segmentos válidos para comparar."}
        ranked = grouped.sort_values(ascending=False).reset_index()
        total = float(ranked["value"].sum())
        leader = float(ranked["value"].iloc[0])
        ranked["share_pct"] = (ranked["value"] / total * 100) if total else 0.0
        ranked["difference_from_leader"] = ranked["value"] - leader
        rows = [{key: (float(value) if hasattr(value, "item") and isinstance(value.item(), (int, float)) else value) for key, value in row.items()} for row in ranked.head(20).to_dict("records")]
        data = {"population": {"rows": len(frame), "valid_rows": len(frame), "missing_rows": 0, "truncated": truncated}, "dimension": dimension, "aggregation": scope.aggregation, "leader": rows[0], "segments": rows, "method": "comparación y ranking de segmentos", "warnings": self._warnings(truncated)}
        data["suggested_blocks"] = [MetricBlock(label=f"Segmento líder: {rows[0][dimension]}", value=f"{rows[0]['value']:,.2f}").model_dump(), TableBlock(title=f"Ranking por {dimension}", columns=list(rows[0]), data=rows).model_dump()]
        return data

    def analyze_trend_scope_pandas(self, database_id: str, *, user_id: int, scope: AnalysisScope) -> dict:
        import pandas as pd
        if scope.time_column is None:
            return {"error": "Indica una columna de fecha para analizar la tendencia."}
        columns = [scope.time_column] + ([scope.metric_column] if scope.metric_column else [])
        frame, truncated = self._scope_frame(database_id, user_id=user_id, scope=scope, columns=columns)
        frame["_date"] = pd.to_datetime(frame[scope.time_column], errors="coerce")
        frame = frame.dropna(subset=["_date"])
        if scope.aggregation == "count":
            frame["_metric"] = 1.0
        else:
            if scope.metric_column is None:
                return {"error": "La agregación seleccionada requiere una métrica."}
            frame["_metric"] = pd.to_numeric(frame[scope.metric_column], errors="coerce")
            frame = frame.dropna(subset=["_metric"])
        frequency = {"day": "D", "week": "W", "month": "MS", "quarter": "QS", "year": "YS"}[scope.time_granularity]
        operation = "sum" if scope.aggregation in {"count", "sum"} else scope.aggregation
        series = frame.set_index("_date")["_metric"].resample(frequency).agg(operation).dropna()
        if len(series) < 2:
            return {"error": "No hay suficientes períodos válidos para calcular una tendencia."}
        changes = series.pct_change() * 100
        total_change = None if series.iloc[0] == 0 else float((series.iloc[-1] - series.iloc[0]) / abs(series.iloc[0]) * 100)
        direction = "up" if series.iloc[-1] > series.iloc[0] else "down" if series.iloc[-1] < series.iloc[0] else "stable"
        rows = [{"period": index.strftime("%Y-%m-%d"), "value": float(value), "change_pct": None if pd.isna(changes.loc[index]) else float(changes.loc[index]), "moving_average": float(series.rolling(3, min_periods=1).mean().loc[index])} for index, value in series.items()]
        data = {"population": {"rows": len(frame), "valid_rows": len(frame), "missing_rows": 0, "truncated": truncated}, "metric": scope.metric_column or "count", "aggregation": scope.aggregation, "granularity": scope.time_granularity, "direction": direction, "total_change_pct": total_change, "periods": rows, "method": "serie temporal agregada con media móvil de tres períodos", "warnings": self._warnings(truncated)}
        data["suggested_blocks"] = [MetricBlock(label="Variación total", value="No comparable" if total_change is None else f"{total_change:+.2f}%").model_dump(), TableBlock(title="Evolución por período", columns=list(rows[0]), data=rows).model_dump()]
        return data

    def detect_outliers_scope_pandas(self, database_id: str, *, user_id: int, scope: AnalysisScope) -> dict:
        import pandas as pd
        result = self.compare_segments_pandas(database_id, user_id=user_id, scope=scope)
        if "error" in result:
            return result
        segments = pd.DataFrame(result["segments"])
        if len(segments) < 4:
            return {"error": "Se requieren al menos cuatro segmentos para evaluar anomalías con fiabilidad."}
        q1, q3 = segments["value"].quantile([0.25, 0.75])
        iqr = q3 - q1
        if iqr == 0:
            return {"population": result["population"], "outliers": [], "method": "IQR", "message": "No se detectaron anomalías: los segmentos comparables tienen valores similares.", "warnings": result["warnings"], "suggested_blocks": [MarkdownBlock(content="No se detectaron anomalías relevantes entre los segmentos analizados.").model_dump()]}
        lower, upper = float(q1 - 1.5 * iqr), float(q3 + 1.5 * iqr)
        outliers: list[dict[str, Any]] = cast(
            list[dict[str, Any]],
            cast(Any, segments[(segments["value"] < lower) | (segments["value"] > upper)]).to_dict("records"),
        )
        data = {"population": result["population"], "dimension": scope.dimension_column, "outliers": outliers, "bounds": {"lower": lower, "upper": upper}, "method": "IQR (1.5 × rango intercuartílico)", "warnings": result["warnings"]}
        data["suggested_blocks"] = [MarkdownBlock(content=("No se detectaron anomalías relevantes." if not outliers else f"Se detectaron {len(outliers)} segmentos fuera del rango esperado.")).model_dump(), TableBlock(title="Segmentos atípicos", columns=list(outliers[0]) if outliers else [scope.dimension_column or "segment", "value"], data=outliers).model_dump()]
        return data

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
