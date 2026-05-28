from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlmodel import Session, col, select

from backend.models import EngineCreate, EngineRead, Engines
from backend.utils.dependencies import get_session

router = APIRouter(prefix="/engines", tags=["engines"])


@router.get(
    "",
    response_model=list[EngineRead],
    summary="List engines",
    description="Return available database engines.",
)
def list_engines(
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    session: Session = Depends(get_session),
):
    stmt = select(Engines).order_by(col(Engines.id).asc()).offset(offset).limit(limit)
    return session.exec(stmt).all()


@router.post(
    "",
    response_model=EngineRead,
    status_code=status.HTTP_201_CREATED,
    summary="Create engine",
    description="Register a new database engine.",
)
def create_engine(payload: EngineCreate, session: Session = Depends(get_session)):
    engine = Engines(**payload.model_dump())
    session.add(engine)
    session.commit()
    session.refresh(engine)
    return engine


@router.get(
    "/{engine_id}",
    response_model=EngineRead,
    summary="Get engine",
    description="Fetch a single engine by id.",
)
def get_engine(engine_id: int, session: Session = Depends(get_session)):
    engine = session.get(Engines, engine_id)
    if not engine:
        raise HTTPException(status_code=404, detail="Engine not found.")
    return engine
