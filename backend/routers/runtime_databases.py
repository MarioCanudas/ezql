from fastapi import (
    APIRouter,
    Depends,
    File,
    Form,
    HTTPException,
    Query,
    UploadFile,
    status,
)

from backend.models import RuntimeDatabaseRead, RuntimeDatabaseSchema
from backend.services.user_database import (
    MAX_UPLOAD_BYTES,
    RuntimeDatabaseError,
    RuntimeDatabaseNotFoundError,
    UserDatabase,
)
from backend.utils.dependencies import get_runtime_database_service

router = APIRouter(prefix="/runtime-databases", tags=["databases"])


@router.get(
    "",
    response_model=list[RuntimeDatabaseRead],
    summary="List temporary databases",
    description="Return SQLite databases loaded in the current backend runtime.",
)
def list_runtime_databases(
    user_id: int | None = Query(default=None),
    service: UserDatabase = Depends(get_runtime_database_service),
):
    return service.list_databases(user_id=user_id)


@router.post(
    "/sample",
    response_model=RuntimeDatabaseRead,
    status_code=status.HTTP_201_CREATED,
    summary="Load sample database",
    description="Register the bundled sample SQLite database for a user session.",
)
def register_sample_database(
    user_id: int = Form(...),
    runtime_id: str | None = Form(default=None),
    service: UserDatabase = Depends(get_runtime_database_service),
):
    return service.register_sample_sqlite(user_id=user_id, runtime_id=runtime_id)


@router.post(
    "/upload",
    response_model=RuntimeDatabaseRead,
    status_code=status.HTTP_201_CREATED,
    summary="Upload temporary SQLite database",
    description="Upload a SQLite database file for the current runtime only.",
)
async def upload_runtime_database(
    user_id: int = Form(...),
    display_name: str = Form(default=""),
    file: UploadFile = File(...),
    runtime_id: str | None = Form(default=None),
    service: UserDatabase = Depends(get_runtime_database_service),
):
    content = await file.read(MAX_UPLOAD_BYTES + 1)
    return service.register_uploaded_sqlite(
        user_id=user_id,
        display_name=display_name,
        filename=file.filename or "database.db",
        content=content,
        runtime_id=runtime_id,
    )


@router.get(
    "/{runtime_db_id}/schema",
    response_model=RuntimeDatabaseSchema,
    summary="Get temporary database schema",
    description="Return schema metadata for a loaded runtime SQLite database.",
)
def get_runtime_database_schema(
    runtime_db_id: str,
    user_id: int = Query(...),
    service: UserDatabase = Depends(get_runtime_database_service),
):
    database = service.get_database(runtime_db_id, user_id=user_id)
    tables = service.get_schema(runtime_db_id, user_id=user_id)
    return RuntimeDatabaseSchema(
        id=database.id,
        name=database.name,
        tables=tables,
        summary=service.get_schema_summary(runtime_db_id, user_id=user_id),
    )


@router.delete(
    "/{runtime_db_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Remove temporary database",
    description="Forget a runtime database and delete the uploaded temporary file when applicable.",
)
def delete_runtime_database(
    runtime_db_id: str,
    user_id: int = Query(...),
    service: UserDatabase = Depends(get_runtime_database_service),
):
    service.remove_database(runtime_db_id, user_id=user_id)
