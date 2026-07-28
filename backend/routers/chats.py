from datetime import datetime
from typing import cast

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import func
from sqlmodel import Session, col, delete, select

from backend.models import (
    AgentRuns,
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
from backend.services.agent.agent_chat import AgentChat, resolve_llm_provider
from backend.services.agent import AnalystAgent
from backend.services.agent.checkpoint import get_checkpoint_store
from backend.services.agent.locks import chat_execution_locks
from backend.services.user_database import UserDatabase
from backend.models.blocks import FlexibleDataBlock
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
    runtime_database_service: UserDatabase = Depends(
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
        runtime_database_service.get_database(
            payload.runtime_db_id,
            user_id=payload.user_id,
        )

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
    runtime_database_service: UserDatabase = Depends(
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

    summary_service: AgentChat
    if chat.runtime_db_id:
        if user_message.id is None:
            raise HTTPException(status_code=500, detail="User message id missing.")
        thread_id = f"chat:{chat_id}:message:{user_message.id}"
        run = AgentRuns(
            chat_id=chat_id,
            message_id=user_message.id,
            thread_id=thread_id,
            status="running",
        )
        session.add(run)
        session.commit()
        try:
            with chat_execution_locks.acquire(chat_id):
                service = AnalystAgent(
                    database_service=runtime_database_service,
                    model_name=model.name,
                    provider=model.company,
                    api_key=api_key,
                )
                summary_service = service.llm_service
                agent_reply = service.generate_reply(
                    user_message=payload.content.text,
                    history=history,
                    summary=chat.summary,
                    runtime_db_id=chat.runtime_db_id,
                    user_id=chat.user_id,
                    thread_id=thread_id,
                )
                assistant_content = Content(
                    text=agent_reply.text,
                    blocks=cast(
                        list[FlexibleDataBlock] | None,
                        agent_reply.blocks,
                    ),
                    # Raw tool payloads remain execution-local. The public
                    # response is represented by blocks and verified metadata.
                    data=None,
                    metadata=agent_reply.metadata,
                )
            run.status = "completed"
            run.completed_at = datetime.now()
            session.add(run)
            session.commit()
        except Exception as exc:
            run.status = "failed"
            run.error_code = type(exc).__name__
            run.completed_at = datetime.now()
            session.add(run)
            session.commit()
            raise
    else:
        service = AgentChat(
            model_name=model.name,
            provider=model.company,
            api_key=api_key,
        )
        summary_service = service
        assistant_text = service.generate_reply(history, summary=chat.summary)
        assistant_content = Content(text=assistant_text, blocks=None, data=None)

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
    except Exception:
        # Summary is a best-effort optimization — never block the response.
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

    thread_ids = list(session.exec(
        select(AgentRuns.thread_id).where(col(AgentRuns.chat_id) == chat_id)
    ).all())
    get_checkpoint_store().delete_threads(thread_ids)
    session.exec(delete(AgentRuns).where(col(AgentRuns.chat_id) == chat_id))
    session.exec(delete(Messages).where(col(Messages.chat_id) == chat_id))
    session.delete(chat)
    session.commit()
