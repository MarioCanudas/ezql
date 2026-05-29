from typing import TYPE_CHECKING

from sqlmodel import Field, Relationship, SQLModel

if TYPE_CHECKING:
    from .databases import Databases


class UserBase(SQLModel):
    name: str = Field(unique=True, max_length=50)


class UserCreate(SQLModel):
    name: str = Field(max_length=50)
    password: str


class UserLogin(UserCreate):
    pass


class UserApiKeysUpdate(SQLModel):
    openai_api_key: str | None = None
    deepseek_api_key: str | None = None


class UserApiKeysRead(SQLModel):
    has_openai_api_key: bool = False
    has_deepseek_api_key: bool = False


class UserRead(UserBase):
    id: int


class Users(UserBase, table=True):
    id: int | None = Field(default=None, primary_key=True)
    hashed_password: str
    openai_api_key: str | None = Field(default=None)
    deepseek_api_key: str | None = Field(default=None)

    databases: list["Databases"] = Relationship(back_populates="user")
