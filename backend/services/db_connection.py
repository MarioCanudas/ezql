import os
from typing import Optional

from pydantic import BaseModel
from sqlalchemy import Engine, event, Inspector, inspect, text
from sqlmodel import Session, SQLModel, Table, create_engine, select

# Import tables to register them with SQLModel metadata
from backend import models  # noqa: F401

DB_URL = "sqlite:///backend/ezql.db"


class _SchemaValidationResult(BaseModel):
    success: bool
    is_empty: bool = False
    missing_tables: set[str] = set()
    extra_tables: set[str] = set()
    message: str = ""
    expected_schema: str = ""


class DBConnection:
    engine: Engine | None = None

    _instance: Optional["DBConnection"] = None

    def __new__(cls) -> "DBConnection":
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance

    def connect(self) -> None:
        """Initializes the database engine and validates the schema."""
        if self.engine is None:
            self.engine = create_engine(DB_URL, echo=os.getenv("EZQL_SQL_ECHO") == "1")
            @event.listens_for(self.engine, "connect")
            def configure_sqlite(connection, _) -> None:
                connection.execute("PRAGMA journal_mode=WAL")
                connection.execute("PRAGMA busy_timeout=5000")
            SQLModel.metadata.create_all(self.engine)
            self._migrate_known_columns()
            self._seed_supported_records()
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
                f"\nExpected SQLModel schema:\n{engine_validation.expected_schema}"
                if engine_validation.expected_schema
                else ""
            )
            raise Exception(f"\n{engine_validation.message}\n{expected_schema}")

    def _migrate_known_columns(self) -> None:
        if self.engine is None:
            return

        inspector = inspect(self.engine)
        table_names = set(inspector.get_table_names())

        if "users" in table_names:
            existing_columns = {
                column["name"] for column in inspector.get_columns("users")
            }
            migrations = {
                "openai_api_key": "ALTER TABLE users ADD COLUMN openai_api_key VARCHAR",
                "deepseek_api_key": "ALTER TABLE users ADD COLUMN deepseek_api_key VARCHAR",
            }
            with self.engine.begin() as connection:
                for column_name, statement in migrations.items():
                    if column_name not in existing_columns:
                        connection.execute(text(statement))

        if "chats" not in table_names:
            return

        chat_columns = inspector.get_columns("chats")
        chat_column_names = {column["name"] for column in chat_columns}
        with self.engine.begin() as connection:
            if "runtime_db_id" not in chat_column_names:
                connection.execute(
                    text("ALTER TABLE chats ADD COLUMN runtime_db_id VARCHAR")
                )
            if "summary_through_message_id" not in chat_column_names:
                connection.execute(text("ALTER TABLE chats ADD COLUMN summary_through_message_id INTEGER"))

        if "agentruns" in table_names:
            run_columns = {column["name"] for column in inspector.get_columns("agentruns")}
            with self.engine.begin() as connection:
                for name, sql_type in {"duration_ms": "INTEGER", "llm_call_count": "INTEGER NOT NULL DEFAULT 0", "tool_call_count": "INTEGER NOT NULL DEFAULT 0", "replan_count": "INTEGER NOT NULL DEFAULT 0"}.items():
                    if name not in run_columns:
                        connection.execute(text(f"ALTER TABLE agentruns ADD COLUMN {name} {sql_type}"))

        refreshed_columns = inspect(self.engine).get_columns("chats")
        db_id_column = next(
            (column for column in refreshed_columns if column["name"] == "db_id"),
            None,
        )
        if db_id_column is not None and not bool(db_id_column.get("nullable", True)):
            self._rebuild_chats_table_with_nullable_db_id()

        if "databases" in table_names:
            db_columns = inspect(self.engine).get_columns("databases")
            user_id_column = next(
                (column for column in db_columns if column["name"] == "user_id"),
                None,
            )
            if user_id_column is not None and not bool(user_id_column.get("nullable", True)):
                self._rebuild_databases_table_with_nullable_user_id()

    def _rebuild_chats_table_with_nullable_db_id(self) -> None:
        if self.engine is None:
            return

        with self.engine.begin() as connection:
            connection.execute(text("PRAGMA foreign_keys=OFF"))
            connection.execute(
                text(
                    "CREATE TABLE chats_new ("
                    "title VARCHAR(50) NOT NULL, "
                    "user_id INTEGER NOT NULL, "
                    "db_id INTEGER, "
                    "runtime_db_id VARCHAR, "
                    "model_id INTEGER NOT NULL, "
                    "summary VARCHAR, "
                    "id INTEGER NOT NULL, "
                    "PRIMARY KEY (id), "
                    "FOREIGN KEY(user_id) REFERENCES users (id), "
                    "FOREIGN KEY(db_id) REFERENCES databases (id), "
                    "FOREIGN KEY(model_id) REFERENCES models (id)"
                    ")"
                )
            )
            connection.execute(
                text(
                    "INSERT INTO chats_new "
                    "(title, user_id, db_id, runtime_db_id, model_id, summary, id) "
                    "SELECT title, user_id, db_id, runtime_db_id, model_id, summary, id "
                    "FROM chats"
                )
            )
            connection.execute(text("DROP TABLE chats"))
            connection.execute(text("ALTER TABLE chats_new RENAME TO chats"))
            connection.execute(
                text("CREATE INDEX IF NOT EXISTS ix_chats_db_id ON chats (db_id)")
            )
            connection.execute(
                text("CREATE INDEX IF NOT EXISTS ix_chats_user_id ON chats (user_id)")
            )
            connection.execute(
                text("CREATE INDEX IF NOT EXISTS ix_chats_model_id ON chats (model_id)")
            )
            connection.execute(
                text(
                    "CREATE INDEX IF NOT EXISTS ix_chats_runtime_db_id ON chats (runtime_db_id)"
                )
            )
            connection.execute(text("PRAGMA foreign_keys=ON"))

    def _rebuild_databases_table_with_nullable_user_id(self) -> None:
        if self.engine is None:
            return

        with self.engine.begin() as connection:
            connection.execute(text("PRAGMA foreign_keys=OFF"))
            connection.execute(
                text(
                    "CREATE TABLE databases_new ("
                    "name VARCHAR(50) NOT NULL, "
                    "user_id INTEGER, "
                    "engine_id INTEGER NOT NULL, "
                    "hashed_db_link VARCHAR NOT NULL, "
                    "hashed_auth_token VARCHAR, "
                    "id INTEGER NOT NULL, "
                    "PRIMARY KEY (id), "
                    "FOREIGN KEY(user_id) REFERENCES users (id), "
                    "FOREIGN KEY(engine_id) REFERENCES engines (id)"
                    ")"
                )
            )
            connection.execute(
                text(
                    "INSERT INTO databases_new "
                    "(name, user_id, engine_id, hashed_db_link, hashed_auth_token, id) "
                    "SELECT name, user_id, engine_id, hashed_db_link, hashed_auth_token, id "
                    "FROM databases"
                )
            )
            connection.execute(text("DROP TABLE databases"))
            connection.execute(text("ALTER TABLE databases_new RENAME TO databases"))
            connection.execute(
                text("CREATE INDEX IF NOT EXISTS ix_databases_user_id ON databases (user_id)")
            )
            connection.execute(
                text("CREATE INDEX IF NOT EXISTS ix_databases_engine_id ON databases (engine_id)")
            )
            connection.execute(text("PRAGMA foreign_keys=ON"))

    def _seed_supported_records(self) -> None:
        if self.engine is None:
            return

        from backend.models import Engines, Models

        with Session(self.engine) as session:
            engines = {
                engine.name.casefold() for engine in session.exec(select(Engines))
            }
            if "sqlite3" not in engines:
                session.add(
                    Engines(
                        name="SQLite3",
                        is_supported=True,
                        agent_context=(
                            "Motor SQLite. Usa solo consultas SELECT o WITH. "
                            "Usa comillas dobles para identificadores con espacios. "
                            "No uses ILIKE, DATE_TRUNC, EXTRACT ni STRING_AGG. "
                            "Para concatenar texto usa || y para condicionales usa CASE WHEN."
                        ),
                    )
                )

            models = {model.name.casefold() for model in session.exec(select(Models))}
            if "gpt-4o-mini" not in models:
                session.add(Models(name="gpt-4o-mini", company="OpenAI"))
            if "deepseek-chat" not in models:
                session.add(Models(name="deepseek-chat", company="DeepSeek"))

            session.commit()

    def _validate_schema(self) -> _SchemaValidationResult:
        if self.engine is None:
            return _SchemaValidationResult(
                success=False,
                is_empty=True,
                message="Database engine is not initialized.",
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
            message_parts.append("Database is empty.")
        else:
            if missing_tables:
                tables_list = "\n".join([f"    - {t}" for t in sorted(missing_tables)])
                message_parts.append(f"Missing tables:\n{tables_list}")

            if extra_tables:
                tables_list = "\n".join([f"    - {t}" for t in sorted(extra_tables)])
                message_parts.append(f"Extra tables found in database:\n{tables_list}")

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

            message_parts.append("Column errors found:\n" + "\n".join(error_details))

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
