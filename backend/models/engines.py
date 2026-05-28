from typing import TYPE_CHECKING

from sqlmodel import Field, Relationship, SQLModel

if TYPE_CHECKING:
    from .databases import Databases


class EngineBase(SQLModel):
    name: str = Field(default="New Engine", max_length=50)
    is_supported: bool = Field(default=False)
    agent_context: str | None = Field(default=None)


class EngineCreate(EngineBase):
    pass


class EngineRead(EngineBase):
    id: int


class Engines(EngineBase, table=True):
    id: int | None = Field(default=None, primary_key=True)

    databases: list["Databases"] = Relationship(back_populates="engine")
