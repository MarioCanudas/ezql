from sqlmodel import Field, SQLModel


class ChatBase(SQLModel):
    title: str = Field(default="New Chat", max_length=50)
    user_id: int = Field(foreign_key="users.id")
    db_id: int = Field(foreign_key="databases.id")
    model_id: int = Field(foreign_key="models.id")
    summary: str | None = Field(default=None)


class Chats(ChatBase, table=True):
    id: int | None = Field(default=None, primary_key=True)
