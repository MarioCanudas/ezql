from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlmodel import Session, col, select

from backend.models import ModelCreate, ModelRead, Models
from backend.utils.dependencies import get_session

router = APIRouter(prefix="/models", tags=["models"])


@router.get(
    "",
    response_model=list[ModelRead],
    summary="List models",
    description="Return available LLM models.",
)
def list_models(
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    session: Session = Depends(get_session),
):
    stmt = select(Models).order_by(col(Models.id).asc()).offset(offset).limit(limit)
    return session.exec(stmt).all()


@router.post(
    "",
    response_model=ModelRead,
    status_code=status.HTTP_201_CREATED,
    summary="Create model",
    description="Register a new LLM model.",
)
def create_model(payload: ModelCreate, session: Session = Depends(get_session)):
    model = Models(**payload.model_dump())
    session.add(model)
    session.commit()
    session.refresh(model)
    return model


@router.get(
    "/{model_id}",
    response_model=ModelRead,
    summary="Get model",
    description="Fetch a single model by id.",
)
def get_model(model_id: int, session: Session = Depends(get_session)):
    model = session.get(Models, model_id)
    if not model:
        raise HTTPException(status_code=404, detail="Model not found.")
    return model
