from sqlmodel import Field, SQLModel


class EngineBase(SQLModel):
    name: str = Field(default="New Engine", max_length=50)
    is_supported: bool = Field(default=False)
    agent_context: str | None = Field(default=None)


class Engines(EngineBase, table=True):
    id: int | None = Field(default=None, primary_key=True)
