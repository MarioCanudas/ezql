from typing import TYPE_CHECKING

from sqlmodel import Field, Relationship, SQLModel

if TYPE_CHECKING:
    from .databases import Databases


class UserBase(SQLModel):
    name: str = Field(unique=True, max_length=50)


class UserCreate(SQLModel):
    name: str = Field(max_length=50)
    password: str


class UserRead(UserBase):
    id: int


class Users(UserBase, table=True):
    id: int | None = Field(default=None, primary_key=True)
    hashed_password: str

    databases: list["Databases"] = Relationship(back_populates="user")
