from typing import TYPE_CHECKING

from sqlmodel import Field, Relationship, SQLModel

if TYPE_CHECKING:
    from .engines import Engines
    from .users import Users


class DatabaseBase(SQLModel):
    name: str = Field(default="New Database", max_length=50)
    user_id: int = Field(foreign_key="users.id")
    engine_id: int = Field(foreign_key="engines.id")
    hashed_db_link: str
    hashed_auth_token: str | None = Field(default=None)


class DatabaseCreate(DatabaseBase):
    db_link: str
    auth_token: str | None = None


class Databases(DatabaseBase, table=True):
    id: int | None = Field(default=None, primary_key=True)

    user: "Users" = Relationship(back_populates="databases")
    engine: "Engines" = Relationship(back_populates="databases")
