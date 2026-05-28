from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlmodel import Session, col, select

from backend.models import (
    Chats,
    Content,
    MessageCreate,
    MessageRead,
    Messages,
    MessageUpdate,
)
from backend.utils.dependencies import get_session

router = APIRouter(prefix="/chats/{chat_id}/messages", tags=["messages"])


@router.get(
    "",
    response_model=list[MessageRead],
    summary="List messages",
    description="Return messages for a chat in chronological order.",
)
def list_messages(
    chat_id: int,
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    session: Session = Depends(get_session),
):
    chat = session.get(Chats, chat_id)
    if not chat:
        raise HTTPException(status_code=404, detail="Chat not found.")

    stmt = (
        select(Messages)
        .where(col(Messages.chat_id) == chat_id)
        .order_by(col(Messages.sent_at).asc(), col(Messages.id).asc())
        .offset(offset)
        .limit(limit)
    )
    messages = session.exec(stmt).all()
    results: list[MessageRead] = []
    for message in messages:
        if message.id is None:
            raise HTTPException(
                status_code=500,
                detail="Message id missing.",
            )
        results.append(
            MessageRead(
                id=message.id,
                chat_id=message.chat_id,
                role=message.role,
                content=Content.model_validate(message.content),
                sent_at=message.sent_at,
            )
        )
    return results


@router.post(
    "",
    response_model=MessageRead,
    status_code=status.HTTP_201_CREATED,
    summary="Create message",
    description="Add a message to a chat.",
)
def create_message(
    chat_id: int,
    payload: MessageCreate,
    session: Session = Depends(get_session),
):
    chat = session.get(Chats, chat_id)
    if not chat:
        raise HTTPException(status_code=404, detail="Chat not found.")

    message = Messages(
        chat_id=chat_id,
        role=payload.role,
        content=payload.content.model_dump(),
    )
    session.add(message)
    session.commit()
    session.refresh(message)
    if message.id is None:
        raise HTTPException(status_code=500, detail="Message id missing.")
    return MessageRead(
        id=message.id,
        chat_id=message.chat_id,
        role=message.role,
        content=Content.model_validate(message.content),
        sent_at=message.sent_at,
    )


@router.patch(
    "/{message_id}",
    response_model=MessageRead,
    summary="Update message",
    description="Update the content of a message within a chat.",
)
def update_message(
    chat_id: int,
    message_id: int,
    payload: MessageUpdate,
    session: Session = Depends(get_session),
):
    message = session.exec(
        select(Messages).where(
            col(Messages.id) == message_id,
            col(Messages.chat_id) == chat_id,
        )
    ).first()
    if not message:
        raise HTTPException(status_code=404, detail="Message not found.")

    message.content = payload.content.model_dump()
    session.add(message)
    session.commit()
    session.refresh(message)
    if message.id is None:
        raise HTTPException(status_code=500, detail="Message id missing.")
    return MessageRead(
        id=message.id,
        chat_id=message.chat_id,
        role=message.role,
        content=Content.model_validate(message.content),
        sent_at=message.sent_at,
    )


@router.delete(
    "/{message_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Delete message",
    description="Delete a message from a chat.",
)
def delete_message(
    chat_id: int,
    message_id: int,
    session: Session = Depends(get_session),
):
    message = session.exec(
        select(Messages).where(
            col(Messages.id) == message_id,
            col(Messages.chat_id) == chat_id,
        )
    ).first()
    if not message:
        raise HTTPException(status_code=404, detail="Message not found.")

    session.delete(message)
    session.commit()
