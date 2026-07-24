"""Tests for FastAPI global exception handlers defined in main.py."""

from fastapi import APIRouter
from fastapi.testclient import TestClient

from backend.main import app
from backend.services.agent.agent_chat import LLMConfigurationError, LLMGenerationError
from backend.services.user_database import RuntimeDatabaseError, RuntimeDatabaseNotFoundError

# Add test-only routes that trigger each exception type.
_error_router = APIRouter(prefix="/test-errors", tags=["test-errors"])


@_error_router.get("/db-not-found")
def _raise_db_not_found():
    raise RuntimeDatabaseNotFoundError("DB not found")


@_error_router.get("/db-error")
def _raise_db_error():
    raise RuntimeDatabaseError("DB error")


@_error_router.get("/llm-config")
def _raise_llm_config():
    raise LLMConfigurationError("Missing API key")


@_error_router.get("/llm-generation")
def _raise_llm_generation():
    raise LLMGenerationError("Generation failed")


app.include_router(_error_router)


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


class TestGlobalExceptionHandlers:
    """Verify that domain exceptions are mapped to the correct HTTP status codes."""

    def test_runtime_database_not_found_returns_404(self, client: TestClient):
        response = client.get("/test-errors/db-not-found")
        assert response.status_code == 404
        assert "DB not found" in response.json()["detail"]

    def test_runtime_database_error_returns_400(self, client: TestClient):
        response = client.get("/test-errors/db-error")
        assert response.status_code == 400
        assert "DB error" in response.json()["detail"]

    def test_llm_configuration_error_returns_500(self, client: TestClient):
        response = client.get("/test-errors/llm-config")
        assert response.status_code == 500
        assert "Missing API key" in response.json()["detail"]

    def test_llm_generation_error_returns_502(self, client: TestClient):
        response = client.get("/test-errors/llm-generation")
        assert response.status_code == 502
        assert "Generation failed" in response.json()["detail"]
