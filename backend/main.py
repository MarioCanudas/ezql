from contextlib import asynccontextmanager
from pathlib import Path
import logging

from dotenv import load_dotenv
from fastapi import FastAPI, Request, status
from fastapi.responses import JSONResponse

from backend.routers import api_router
from backend.services.user_database import (
    RuntimeDatabaseError,
    RuntimeDatabaseNotFoundError,
)
from backend.services.agent.agent_chat import LLMConfigurationError, LLMGenerationError
from backend.utils.dependencies import ServiceRegistry
from backend.services.agent.checkpoint import close_checkpoint_store

ENV_PATH = Path(__file__).resolve().parents[1] / "frontend" / ".env"
load_dotenv(ENV_PATH)


@asynccontextmanager
async def lifespan(app: FastAPI):
    try:
        print("Connecting to the database...")
        ServiceRegistry.get_db_connection().connect()
        ServiceRegistry.get_user_database()  # Initialize the registry instance
        print("Database connection established.")
        yield
    except Exception as e:
        print(f"Error during database connection: {e}")
    finally:
        print("Cleaning up services...")
        close_checkpoint_store()
        ServiceRegistry.clear()
        print("Services cleanup complete.")


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


@app.exception_handler(RuntimeDatabaseNotFoundError)
async def runtime_database_not_found_handler(
    request: Request, exc: RuntimeDatabaseNotFoundError
):
    return JSONResponse(
        status_code=status.HTTP_404_NOT_FOUND,
        content={"detail": str(exc)},
    )


@app.exception_handler(RuntimeDatabaseError)
async def runtime_database_error_handler(request: Request, exc: RuntimeDatabaseError):
    return JSONResponse(
        status_code=status.HTTP_400_BAD_REQUEST,
        content={"detail": str(exc)},
    )


@app.exception_handler(LLMConfigurationError)
async def llm_configuration_error_handler(request: Request, exc: LLMConfigurationError):
    return JSONResponse(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        content={"detail": str(exc)},
    )


logger = logging.getLogger(__name__)


@app.exception_handler(LLMGenerationError)
async def llm_generation_error_handler(request: Request, exc: LLMGenerationError):
    logger.exception("LLM generation error: %s", exc)
    return JSONResponse(
        status_code=status.HTTP_502_BAD_GATEWAY,
        content={
            "detail": str(exc)
            if str(exc)
            else "The assistant could not generate a response. Please try again."
        },
    )


app.include_router(api_router, prefix="/api/v1")
