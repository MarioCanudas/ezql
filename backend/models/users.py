from sqlmodel import Field, SQLModel


class UserBase(SQLModel):
    name: str = Field(unique=True, max_length=50)
    hashed_password: str


class UserCreate(UserBase):
    password: str


class Users(UserBase, table=True):
    id: int | None = Field(default=None, primary_key=True)
