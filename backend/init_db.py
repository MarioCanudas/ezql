from sqlmodel import Session, SQLModel, create_engine, select

from backend import models  # noqa: F401
from backend.services.db_connection import DB_URL


def init_db():
    engine = create_engine(DB_URL, echo=True)
    print(f"Initializing database at {DB_URL}...")
    SQLModel.metadata.create_all(engine)

    from backend.models import Engines, Models

    with Session(engine) as session:
        engines = {engine.name.casefold() for engine in session.exec(select(Engines))}
        if "sqlite3" not in engines:
            session.add(
                Engines(
                    name="SQLite3",
                    is_supported=True,
                    agent_context="Usa sintaxis compatible con SQLite.",
                )
            )

        model_names = {model.name.casefold() for model in session.exec(select(Models))}
        if "gpt-4o-mini" not in model_names:
            session.add(Models(name="gpt-4o-mini", company="OpenAI"))
        if "deepseek-chat" not in model_names:
            session.add(Models(name="deepseek-chat", company="DeepSeek"))
        session.commit()

    print("Database initialized successfully.")


if __name__ == "__main__":
    init_db()
