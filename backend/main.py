from contextlib import asynccontextmanager
from pathlib import Path

from dotenv import load_dotenv
from fastapi import FastAPI

from backend.routers import api_router
from backend.services import DBConnectionService

ENV_PATH = Path(__file__).resolve().parents[1] / "frontend" / ".env"
load_dotenv(ENV_PATH)


@asynccontextmanager
async def lifespan(app: FastAPI):
    db_service = DBConnectionService()

    try:
        print("Connecting to the database...")
        db_service.connect()
        app.state.db_service = db_service
        print("Database connection established.")
        yield
    except Exception as e:
        print(f"Error during database connection: {e}")
    finally:
        print("Disconnecting from the database...")
        db_service.disconnect()
        print("Database connection closed.")


tags_metadata = [
    {
        "name": "chats",
        "description": "Create chats and keep a fast chat list with activity metadata.",
    },
    {"name": "messages", "description": "Append and read chat messages."},
    {"name": "users", "description": "User profiles for owning chats and databases."},
    {
        "name": "databases",
        "description": "Database connections (stored as hashed secrets).",
    },
    {"name": "engines", "description": "Supported database engines."},
    {"name": "models", "description": "LLM models available to the chat agent."},
]

app = FastAPI(
    title="EzQL API",
    version="0.0.1",
    description=(
        "API backend for EzQL. Provides chat persistence, database metadata, and "
        "model management endpoints for the Streamlit frontend."
    ),
    openapi_tags=tags_metadata,
    lifespan=lifespan,
)

app.include_router(api_router, prefix="/api/v1")
