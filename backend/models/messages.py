from datetime import datetime
from enum import Enum
from typing import TypeAlias

from pydantic import BaseModel
from sqlmodel import JSON, Field, SQLModel


JSONValue: TypeAlias = (
    str | int | float | bool | None | list["JSONValue"] | dict[str, "JSONValue"]
)


class Role(str, Enum):
    user = "user"
    assistant = "agent"


class Content(BaseModel):
    text: str
    data: list[dict[str, JSONValue]] | None = None


class MessageBase(SQLModel):
    chat_id: int = Field(foreign_key="chats.id", index=True)
    role: Role

    # To ensure SQLModel treats this as a JSON column, we set sa_type=JSON
    # and use a standard Python dict for the content. SQLModel will handle the
    # serialization/deserialization to JSON when interacting with the database.
    # But alongside that, we also define a Pydantic model (Content) to enforce
    # the structure of the content data in our application logic.
    content: dict[str, JSONValue] = Field(sa_type=JSON)

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


class Messages(MessageBase, table=True):
    id: int | None = Field(default=None, primary_key=True)
