from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import func
from sqlmodel import Session, col, delete, select

from backend.models import (
    ChatCreate,
    ChatRead,
    ChatReplyRequest,
    ChatReplyResponse,
    Chats,
    ChatSummary,
    ChatUpdate,
    Content,
    Databases,
    MessageRead,
    Messages,
    Models,
    Role,
    Users,
)
from backend.services.llm_chat_service import (
    LLMChatService,
    LLMConfigurationError,
    LLMGenerationError,
    resolve_llm_provider,
)
from backend.services.sql_agent_service import SQLAgentService
from backend.services.user_database_service import (
    RuntimeDatabaseError,
    RuntimeDatabaseNotFoundError,
    UserDatabaseService,
)
from backend.utils.dependencies import get_runtime_database_service, get_session

router = APIRouter(prefix="/chats", tags=["chats"])


def _to_message_read(message: Messages) -> MessageRead:
    if message.id is None:
        raise HTTPException(status_code=500, detail="Message id missing.")
    return MessageRead(
        id=message.id,
        chat_id=message.chat_id,
        role=message.role,
        content=Content.model_validate(message.content),
        sent_at=message.sent_at,
    )


@router.get(
    "",
    response_model=list[ChatSummary],
    summary="List chats",
    description="Return chats with message counts and last activity to render a chat list efficiently.",
)
def list_chats(
    user_id: int | None = Query(default=None),
    db_id: int | None = Query(default=None),
    model_id: int | None = Query(default=None),
    limit: int = Query(default=20, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
    session: Session = Depends(get_session),
):
    message_count = func.count(col(Messages.id))
    last_message_at = func.max(col(Messages.sent_at))
    stmt = (
        select(Chats, message_count, last_message_at)
        .outerjoin(Messages, col(Messages.chat_id) == col(Chats.id))
        .group_by(col(Chats.id))
    )
    if user_id is not None:
        stmt = stmt.where(col(Chats.user_id) == user_id)
    if db_id is not None:
        stmt = stmt.where(col(Chats.db_id) == db_id)
    if model_id is not None:
        stmt = stmt.where(col(Chats.model_id) == model_id)

    stmt = (
        stmt.order_by(last_message_at.desc(), col(Chats.id).desc())
        .offset(offset)
        .limit(limit)
    )

    results = session.exec(stmt).all()
    return [
        ChatSummary(
            **chat.model_dump(),
            message_count=int(message_count or 0),
            last_message_at=last_message_at,
        )
        for chat, message_count, last_message_at in results
    ]


@router.post(
    "",
    response_model=ChatRead,
    status_code=status.HTTP_201_CREATED,
    summary="Create chat",
    description="Create a chat linked to a user, database, and model.",
)
def create_chat(
    payload: ChatCreate,
    session: Session = Depends(get_session),
    runtime_database_service: UserDatabaseService = Depends(
        get_runtime_database_service
    ),
):
    user = session.get(Users, payload.user_id)
    if not user:
        raise HTTPException(status_code=404, detail="User not found.")

    if payload.db_id is None and payload.runtime_db_id is None:
        raise HTTPException(
            status_code=400,
            detail="Selecciona una base de datos para crear el chat.",
        )

    if payload.db_id is not None:
        db = session.get(Databases, payload.db_id)
        if not db:
            raise HTTPException(status_code=404, detail="Database not found.")
        if db.user_id is not None and db.user_id != payload.user_id:
            raise HTTPException(
                status_code=400,
                detail="Database does not belong to the selected user.",
            )

    if payload.runtime_db_id is not None:
        try:
            runtime_database_service.get_database(
                payload.runtime_db_id,
                user_id=payload.user_id,
            )
        except RuntimeDatabaseNotFoundError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        except RuntimeDatabaseError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc

    model = session.get(Models, payload.model_id)
    if not model:
        raise HTTPException(status_code=404, detail="Model not found.")

    chat = Chats(**payload.model_dump())
    session.add(chat)
    session.commit()
    session.refresh(chat)
    return chat


@router.get(
    "/{chat_id}",
    response_model=ChatRead,
    summary="Get chat",
    description="Fetch a single chat by id.",
)
def get_chat(chat_id: int, session: Session = Depends(get_session)):
    chat = session.get(Chats, chat_id)
    if not chat:
        raise HTTPException(status_code=404, detail="Chat not found.")
    return chat


@router.patch(
    "/{chat_id}",
    response_model=ChatRead,
    summary="Update chat",
    description="Update a chat title and/or summary.",
)
def update_chat(
    chat_id: int,
    payload: ChatUpdate,
    session: Session = Depends(get_session),
):
    chat = session.get(Chats, chat_id)
    if not chat:
        raise HTTPException(status_code=404, detail="Chat not found.")

    updates = payload.model_dump(exclude_unset=True)
    for key, value in updates.items():
        setattr(chat, key, value)

    session.add(chat)
    session.commit()
    session.refresh(chat)
    return chat


@router.post(
    "/{chat_id}/reply",
    response_model=ChatReplyResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Generate reply",
    description="Store a user message, generate an assistant reply, and persist both.",
)
def generate_reply(
    chat_id: int,
    payload: ChatReplyRequest,
    session: Session = Depends(get_session),
    runtime_database_service: UserDatabaseService = Depends(
        get_runtime_database_service
    ),
):
    chat = session.get(Chats, chat_id)
    if not chat:
        raise HTTPException(status_code=404, detail="Chat not found.")
    if payload.user_id is not None and payload.user_id != chat.user_id:
        raise HTTPException(
            status_code=400,
            detail="Chat does not belong to the selected user.",
        )
    if not payload.content.text.strip():
        raise HTTPException(status_code=400, detail="Message content is required.")

    model = session.get(Models, chat.model_id)
    if not model:
        raise HTTPException(status_code=404, detail="Model not found.")

    user = session.get(Users, chat.user_id)
    if not user:
        raise HTTPException(status_code=404, detail="User not found.")

    provider = resolve_llm_provider(model.company, model.name)
    api_key = user.deepseek_api_key if provider == "deepseek" else user.openai_api_key
    if not api_key:
        raise HTTPException(
            status_code=400,
            detail="Configure the selected model provider API key in your profile.",
        )

    user_message = Messages(
        chat_id=chat_id,
        role=Role.user,
        content=payload.content.model_dump(),
    )
    session.add(user_message)
    session.commit()
    session.refresh(user_message)

    history = session.exec(
        select(Messages)
        .where(col(Messages.chat_id) == chat_id)
        .order_by(col(Messages.sent_at).asc(), col(Messages.id).asc())
    ).all()

    summary_service: LLMChatService
    if chat.runtime_db_id:
        service = SQLAgentService(
            database_service=runtime_database_service,
            model_name=model.name,
            provider=model.company,
            api_key=api_key,
        )
        summary_service = service.llm_service
        try:
            agent_reply = service.generate_reply(
                user_message=payload.content.text,
                history=history,
                summary=chat.summary,
                runtime_db_id=chat.runtime_db_id,
                user_id=chat.user_id,
            )
        except LLMConfigurationError as exc:
            raise HTTPException(status_code=500, detail=str(exc)) from exc
        except LLMGenerationError as exc:
            raise HTTPException(
                status_code=502,
                detail="The assistant could not generate a response. Please try again.",
            ) from exc
        assistant_content = Content(text=agent_reply.text, data=agent_reply.data)
    else:
        service = LLMChatService(
            model_name=model.name,
            provider=model.company,
            api_key=api_key,
        )
        summary_service = service
        try:
            assistant_text = service.generate_reply(history, summary=chat.summary)
        except LLMConfigurationError as exc:
            raise HTTPException(status_code=500, detail=str(exc)) from exc
        except LLMGenerationError as exc:
            raise HTTPException(
                status_code=502,
                detail="The assistant could not generate a response. Please try again.",
            ) from exc
        assistant_content = Content(text=assistant_text, data=None)

    assistant_message = Messages(
        chat_id=chat_id,
        role=Role.assistant,
        content=assistant_content.model_dump(),
    )
    session.add(assistant_message)
    session.commit()
    session.refresh(assistant_message)

    updated_history = [*history, assistant_message]
    try:
        chat.summary = summary_service.summarize_chat(
            updated_history,
            current_summary=chat.summary,
        )
        session.add(chat)
        session.commit()
    except LLMGenerationError:
        session.rollback()

    return ChatReplyResponse(
        user_message=_to_message_read(user_message),
        assistant_message=_to_message_read(assistant_message),
    )


@router.delete(
    "/{chat_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Delete chat",
    description="Delete a chat and its associated messages.",
)
def delete_chat(chat_id: int, session: Session = Depends(get_session)):
    chat = session.get(Chats, chat_id)
    if not chat:
        raise HTTPException(status_code=404, detail="Chat not found.")

    session.exec(delete(Messages).where(col(Messages.chat_id) == chat_id))
    session.delete(chat)
    session.commit()
