from fastapi import Request
from sqlmodel import Session


def get_session(request: Request):
    """Dependency that provides a SQLModely session to interact with the database."""
    with Session(request.app.state.db_service.engine) as session:
        yield session


def get_runtime_database_service(request: Request):
    """Dependency that provides access to temporary user SQLite databases."""
    return request.app.state.user_database_service
