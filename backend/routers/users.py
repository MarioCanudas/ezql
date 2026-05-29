from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlmodel import Session, col, select

from backend.models import (
    UserApiKeysRead,
    UserApiKeysUpdate,
    UserCreate,
    UserLogin,
    UserRead,
    Users,
)
from backend.utils.dependencies import get_session
from backend.utils.security import hash_password, password_needs_rehash, verify_password

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

    user = Users(name=payload.name, hashed_password=hash_password(payload.password))
    session.add(user)
    session.commit()
    session.refresh(user)
    return user


@router.post(
    "/login",
    response_model=UserRead,
    summary="Login user",
    description="Verify user credentials and return the matching user.",
)
def login_user(payload: UserLogin, session: Session = Depends(get_session)):
    user = session.exec(select(Users).where(Users.name == payload.name)).first()
    if not user or not verify_password(payload.password, user.hashed_password):
        raise HTTPException(status_code=401, detail="Invalid user name or password.")

    if password_needs_rehash(user.hashed_password):
        user.hashed_password = hash_password(payload.password)
        session.add(user)
        session.commit()
        session.refresh(user)

    return user


@router.get(
    "/{user_id}/api-keys",
    response_model=UserApiKeysRead,
    summary="Get user API key status",
    description="Return which LLM provider API keys are configured for a user.",
)
def get_user_api_keys(user_id: int, session: Session = Depends(get_session)):
    user = session.get(Users, user_id)
    if not user:
        raise HTTPException(status_code=404, detail="User not found.")
    return UserApiKeysRead(
        has_openai_api_key=bool(user.openai_api_key),
        has_deepseek_api_key=bool(user.deepseek_api_key),
    )


@router.put(
    "/{user_id}/api-keys",
    response_model=UserApiKeysRead,
    summary="Update user API keys",
    description="Store the user's LLM provider API keys.",
)
def update_user_api_keys(
    user_id: int,
    payload: UserApiKeysUpdate,
    session: Session = Depends(get_session),
):
    user = session.get(Users, user_id)
    if not user:
        raise HTTPException(status_code=404, detail="User not found.")

    if payload.openai_api_key is not None:
        user.openai_api_key = payload.openai_api_key.strip() or None
    if payload.deepseek_api_key is not None:
        user.deepseek_api_key = payload.deepseek_api_key.strip() or None
    session.add(user)
    session.commit()
    session.refresh(user)
    return UserApiKeysRead(
        has_openai_api_key=bool(user.openai_api_key),
        has_deepseek_api_key=bool(user.deepseek_api_key),
    )


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
