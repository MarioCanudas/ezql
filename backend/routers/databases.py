from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlmodel import Session, col, select

from backend.models import DatabaseCreate, DatabaseRead, Databases, Engines, Users
from backend.utils.dependencies import get_session
from backend.utils.security import hash_secret

router = APIRouter(prefix="/databases", tags=["databases"])


@router.get(
    "",
    response_model=list[DatabaseRead],
    summary="List databases",
    description="Return databases with optional filtering by user or engine.",
)
def list_databases(
    user_id: int | None = Query(default=None),
    engine_id: int | None = Query(default=None),
    limit: int = Query(default=20, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
    session: Session = Depends(get_session),
):
    stmt = select(Databases)
    if user_id is not None:
        stmt = stmt.where((col(Databases.user_id) == user_id) | (col(Databases.user_id) == None))
    if engine_id is not None:
        stmt = stmt.where(col(Databases.engine_id) == engine_id)

    stmt = stmt.order_by(col(Databases.id).asc()).offset(offset).limit(limit)
    return session.exec(stmt).all()


@router.post(
    "",
    response_model=DatabaseRead,
    status_code=status.HTTP_201_CREATED,
    summary="Create database",
    description="Create a database entry and store hashed connection data.",
)
def create_database(payload: DatabaseCreate, session: Session = Depends(get_session)):
    user = session.get(Users, payload.user_id)
    if not user:
        raise HTTPException(status_code=404, detail="User not found.")

    engine = session.get(Engines, payload.engine_id)
    if not engine:
        raise HTTPException(status_code=404, detail="Engine not found.")

    db = Databases(
        name=payload.name,
        user_id=payload.user_id,
        engine_id=payload.engine_id,
        hashed_db_link=hash_secret(payload.db_link),
        hashed_auth_token=hash_secret(payload.auth_token)
        if payload.auth_token
        else None,
    )
    session.add(db)
    session.commit()
    session.refresh(db)
    return db


@router.get(
    "/{db_id}",
    response_model=DatabaseRead,
    summary="Get database",
    description="Fetch a single database by id.",
)
def get_database(db_id: int, session: Session = Depends(get_session)):
    db = session.get(Databases, db_id)
    if not db:
        raise HTTPException(status_code=404, detail="Database not found.")
    return db
