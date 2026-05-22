from typing import TYPE_CHECKING

from sqlmodel import Field, Relationship, SQLModel

if TYPE_CHECKING:
    from .databases import Databases


class UserBase(SQLModel):
    name: str = Field(unique=True, max_length=50)
    hashed_password: str


class UserCreate(UserBase):
    password: str


class Users(UserBase, table=True):
    id: int | None = Field(default=None, primary_key=True)

    databases: list["Databases"] = Relationship(back_populates="user")
