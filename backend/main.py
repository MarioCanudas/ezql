from contextlib import asynccontextmanager

from fastapi import FastAPI
from services import DBConnectionService


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


app = FastAPI(lifespan=lifespan)
