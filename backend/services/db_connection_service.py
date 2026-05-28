from typing import Optional

# Import tables to register them with SQLModel metadata
import models  # noqa: F401
from pydantic import BaseModel
from sqlalchemy import Engine, Inspector, inspect
from sqlmodel import SQLModel, Table, create_engine

DB_URL = "sqlite:///backend/ezql.db"


class _SchemaValidationResult(BaseModel):
    success: bool
    is_empty: bool = False
    missing_tables: set[str] = set()
    extra_tables: set[str] = set()
    message: str = ""
    expected_schema: str = ""


class DBConnectionService:
    engine: Engine | None = None

    _instance: Optional["DBConnectionService"] = None

    def __new__(cls) -> "DBConnectionService":
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance

    def connect(self) -> None:
        """Initializes the database engine and validates the schema."""
        if self.engine is None:
            self.engine = create_engine(DB_URL, echo=True)
            self.validate_or_raise()

    def disconnect(self) -> None:
        """Disposes the database engine."""
        if self.engine is not None:
            self.engine.dispose()
            self.engine = None

    def validate_or_raise(self) -> None:
        engine_validation = self._validate_schema()
        if not engine_validation.success:
            expected_schema = (
                f"\n💡 Expected SQLModel schema:\n{engine_validation.expected_schema}"
                if engine_validation.expected_schema
                else ""
            )
            raise Exception(f"\n{engine_validation.message}\n{expected_schema}")

    def _validate_schema(self) -> _SchemaValidationResult:
        if self.engine is None:
            return _SchemaValidationResult(
                success=False,
                is_empty=True,
                message="❌ Database engine is not initialized.",
            )

        inspector = inspect(self.engine)
        tables_schema = SQLModel.metadata.tables

        db_tables = set(inspector.get_table_names())
        expected_tables = set(SQLModel.metadata.tables.keys())
        expected_schema = self._describe_expected_schema(tables_schema)

        missing_tables = expected_tables - db_tables
        extra_tables = db_tables - expected_tables
        is_empty = len(db_tables) == 0

        message_parts: list[str] = []
        if is_empty:
            message_parts.append("⚠️ Database is empty.")
        else:
            if missing_tables:
                tables_list = "\n".join([f"    - {t}" for t in sorted(missing_tables)])
                message_parts.append(f"❌ Missing tables:\n{tables_list}")

            if extra_tables:
                tables_list = "\n".join([f"    - {t}" for t in sorted(extra_tables)])
                message_parts.append(
                    f"❌ Extra tables found in database:\n{tables_list}"
                )

        table_errors: dict[str, list[str]] = {}
        if not bool(missing_tables):
            for table in tables_schema.values():
                column_errors = self._verify_table_columns(inspector, table)
                if column_errors:
                    table_errors[table.name] = column_errors

        if table_errors:
            error_details: list[str] = []
            for table, errors in table_errors.items():
                formatted_errors = "\n".join([f"      - {e}" for e in errors])
                error_details.append(f"    Table '{table}':\n{formatted_errors}")

            message_parts.append("❌ Column errors found:\n" + "\n".join(error_details))

        success = (
            not is_empty
            and not missing_tables
            and not extra_tables
            and not table_errors
        )

        result = _SchemaValidationResult(
            success=success,
            is_empty=is_empty,
            missing_tables=missing_tables,
            extra_tables=extra_tables,
            message="\n".join(message_parts),
            expected_schema=expected_schema,
        )

        return result

    def _describe_expected_schema(self, tables_schema: dict[str, Table]) -> str:
        table_descriptions: list[str] = []
        for table in tables_schema.values():
            column_descriptions: list[str] = []
            for column in table.columns:
                pk_suffix = " (PK)" if column.primary_key else ""
                column_descriptions.append(
                    f"    - {column.name}: {column.type}{pk_suffix}"
                )

            table_header = f"  Table '{table.name}':"
            table_descriptions.append(
                f"{table_header}\n" + "\n".join(column_descriptions)
            )

        return "\n".join(table_descriptions)

    def _verify_table_columns(self, inspector: Inspector, table: Table) -> list[str]:
        expected_schema: dict[str, str] = {}
        for col in table.columns:
            expected_schema[col.name] = str(col.type)

        engine_schema: dict[str, str] = {}
        for col in inspector.get_columns(table.name):
            engine_schema[col["name"]] = str(col["type"])

        errors: list[str] = []

        missing_columns = set(expected_schema.keys()) - set(engine_schema.keys())
        for col_name in sorted(missing_columns):
            errors.append(
                f"missing column '{col_name}' "
                f"(expected type: {expected_schema[col_name]})"
            )

        extra_columns = set(engine_schema.keys()) - set(expected_schema.keys())
        for col_name in sorted(extra_columns):
            errors.append(
                f"extra column '{col_name}' (engine type: {engine_schema[col_name]})"
            )

        common_columns = set(expected_schema.keys()) & set(engine_schema.keys())
        for col_name in sorted(common_columns):
            expected_type = expected_schema[col_name]
            engine_type = engine_schema[col_name]
            if expected_type != engine_type:
                errors.append(
                    f"type mismatch in column '{col_name}' "
                    f"(expected: {expected_type}, engine: {engine_type})"
                )

        return errors
