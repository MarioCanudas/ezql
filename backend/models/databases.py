from sqlmodel import Field, SQLModel


class DatabaseBase(SQLModel):
    name: str = Field(default="New Database", max_length=50)
    user_id: int = Field(foreign_key="users.id")
    engine_id: int = Field(foreign_key="engines.id")
    hashed_db_link: str


class DatabaseCreate(DatabaseBase):
    db_link: str


class Databases(DatabaseBase, table=True):
    id: int | None = Field(default=None, primary_key=True)
