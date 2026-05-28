from typing import TYPE_CHECKING

from sqlmodel import Field, Relationship, SQLModel

if TYPE_CHECKING:
    from .engines import Engines
    from .users import Users


class DatabaseBase(SQLModel):
    name: str = Field(default="New Database", max_length=50)
    user_id: int = Field(foreign_key="users.id", index=True)
    engine_id: int = Field(foreign_key="engines.id", index=True)


class DatabaseCreate(SQLModel):
    name: str = Field(default="New Database", max_length=50)
    user_id: int
    engine_id: int
    db_link: str = Field(min_length=1)
    auth_token: str | None = None


class DatabaseRead(DatabaseBase):
    id: int


class Databases(DatabaseBase, table=True):
    id: int | None = Field(default=None, primary_key=True)
    hashed_db_link: str
    hashed_auth_token: str | None = Field(default=None)

    user: "Users" = Relationship(back_populates="databases")
    engine: "Engines" = Relationship(back_populates="databases")
