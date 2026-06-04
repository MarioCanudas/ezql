from datetime import datetime

from sqlmodel import Field, SQLModel


class ChatBase(SQLModel):
    title: str = Field(default="New Chat", max_length=50)
    user_id: int = Field(foreign_key="users.id", index=True)
    db_id: int | None = Field(default=None, foreign_key="databases.id", index=True)
    runtime_db_id: str | None = Field(default=None, index=True)
    model_id: int = Field(foreign_key="models.id", index=True)
    summary: str | None = Field(default=None)


class ChatCreate(ChatBase):
    pass


class ChatUpdate(SQLModel):
    title: str | None = Field(default=None, max_length=50)
    summary: str | None = Field(default=None)
    runtime_db_id: str | None = Field(default=None)
    db_id: int | None = Field(default=None)


class ChatRead(ChatBase):
    id: int


class ChatSummary(ChatBase):
    id: int
    message_count: int = 0
    last_message_at: datetime | None = None


class Chats(ChatBase, table=True):
    id: int | None = Field(default=None, primary_key=True)
