from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlmodel import Session, col, select

from backend.models import UserCreate, UserRead, Users
from backend.utils.dependencies import get_session
from backend.utils.security import hash_secret

router = APIRouter(prefix="/users", tags=["users"])


@router.get(
    "",
    response_model=list[UserRead],
    summary="List users",
    description="Return users with pagination.",
)
def list_users(
    limit: int = Query(default=20, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
    session: Session = Depends(get_session),
):
    stmt = select(Users).order_by(col(Users.id).asc()).offset(offset).limit(limit)
    return session.exec(stmt).all()


@router.post(
    "",
    response_model=UserRead,
    status_code=status.HTTP_201_CREATED,
    summary="Create user",
    description="Create a user and store a hashed password.",
)
def create_user(payload: UserCreate, session: Session = Depends(get_session)):
    existing = session.exec(select(Users).where(Users.name == payload.name)).first()
    if existing:
        raise HTTPException(status_code=409, detail="User name already exists.")

    user = Users(name=payload.name, hashed_password=hash_secret(payload.password))
    session.add(user)
    session.commit()
    session.refresh(user)
    return user


@router.get(
    "/{user_id}",
    response_model=UserRead,
    summary="Get user",
    description="Fetch a single user by id.",
)
def get_user(user_id: int, session: Session = Depends(get_session)):
    user = session.get(Users, user_id)
    if not user:
        raise HTTPException(status_code=404, detail="User not found.")
    return user
