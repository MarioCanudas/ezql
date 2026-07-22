from sqlmodel import Session

from backend.services.user_database import UserDatabase
from backend.services.db_connection import DBConnection


class ServiceRegistry:
    """
    Registry pattern for managing application-level singleton services.
    Ensures safe and controlled access to shared instances without relying on app.state.
    """
    _user_database: UserDatabase | None = None
    _db_connection: DBConnection | None = None

    @classmethod
    def get_user_database(cls) -> UserDatabase:
        if cls._user_database is None:
            cls._user_database = UserDatabase()
        return cls._user_database

    @classmethod
    def get_db_connection(cls) -> DBConnection:
        if cls._db_connection is None:
            cls._db_connection = DBConnection()
        return cls._db_connection
    
    @classmethod
    def clear(cls):
        """Cleans up the registry. Called during shutdown."""
        if cls._user_database:
            cls._user_database.close()
            cls._user_database = None
        if cls._db_connection:
            cls._db_connection.disconnect()
            cls._db_connection = None


def get_session():
    """Dependency that provides a SQLModel session to interact with the database."""
    engine = ServiceRegistry.get_db_connection().engine
    with Session(engine) as session:
        yield session


def get_runtime_database_service() -> UserDatabase:
    """Dependency that provides access to temporary user SQLite databases."""
    return ServiceRegistry.get_user_database()
