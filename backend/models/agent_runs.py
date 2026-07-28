from __future__ import annotations

from datetime import datetime
from typing import Literal

from sqlmodel import Field, SQLModel


RunStatus = Literal["running", "completed", "failed"]


class AgentRunBase(SQLModel):
    chat_id: int = Field(foreign_key="chats.id", index=True)
    message_id: int = Field(foreign_key="messages.id", index=True)
    thread_id: str = Field(index=True, unique=True, max_length=200)
    status: str = Field(default="running", max_length=20)
    attempt: int = Field(default=1, ge=1)
    error_code: str | None = Field(default=None, max_length=100)
    started_at: datetime = Field(default_factory=datetime.now)
    completed_at: datetime | None = Field(default=None)


class AgentRuns(AgentRunBase, table=True):
    id: int | None = Field(default=None, primary_key=True)
