from datetime import datetime
from enum import Enum

from pydantic import BaseModel
from sqlmodel import JSON, Field, SQLModel


class Role(Enum):
    user = "user"
    assistant = "agent"


class Content(BaseModel):
    text: str
    data: list[dict[str, str]] | None = None


class MessageBase(SQLModel):
    chat_id: int = Field(foreign_key="chats.id")
    role: Role
    content: Content = Field(sa_type=JSON)
    sent_at: datetime = Field(default_factory=datetime.now)


class Messages(MessageBase, table=True):
    id: int | None = Field(default=None, primary_key=True)
