from fastapi import Request
from sqlmodel import Session


def get_session(request: Request):
    """Dependency that provides a SQLModely session to interact with the database."""
    with Session(request.app.state.db_service.engine) as session:
        yield session
