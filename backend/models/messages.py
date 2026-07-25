from datetime import datetime
from enum import Enum

from pydantic import BaseModel, JsonValue
from sqlmodel import JSON, Field, SQLModel


class Role(str, Enum):
    user = "user"
    assistant = "agent"


from backend.models.blocks import FlexibleDataBlock

class Content(BaseModel):
    text: str
    blocks: list[FlexibleDataBlock] | None = None
    data: list[FlexibleDataBlock] | None = None



class MessageBase(SQLModel):
    chat_id: int = Field(foreign_key="chats.id", index=True)
    role: Role

    # To ensure SQLModel treats this as a JSON column, we set sa_type=JSON
    # and use a standard Python dict for the content. SQLModel will handle the
    # serialization/deserialization to JSON when interacting with the database.
    # But alongside that, we also define a Pydantic model (Content) to enforce
    # the structure of the content data in our application logic.
    content: dict[str, JsonValue] = Field(sa_type=JSON)

    sent_at: datetime = Field(default_factory=datetime.now, index=True)


class MessageCreate(SQLModel):
    role: Role
    content: Content


class MessageUpdate(SQLModel):
    content: Content


class MessageRead(SQLModel):
    id: int
    chat_id: int
    role: Role
    content: Content
    sent_at: datetime


class ChatReplyRequest(BaseModel):
    content: Content
    user_id: int | None = None


class ChatReplyResponse(BaseModel):
    user_message: MessageRead
    assistant_message: MessageRead


class Messages(MessageBase, table=True):
    id: int | None = Field(default=None, primary_key=True)
