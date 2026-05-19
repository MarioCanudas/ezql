import models  # noqa: F401
from sqlmodel import SQLModel, create_engine

DB_URL = "sqlite:///backend/ezql.db"


def init_db():
    engine = create_engine(DB_URL, echo=True)
    print(f"Initializing database at {DB_URL}...")
    SQLModel.metadata.create_all(engine)
    print("Database initialized successfully.")


if __name__ == "__main__":
    init_db()
