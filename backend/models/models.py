from sqlmodel import Field, SQLModel


class ModelBase(SQLModel):
    name: str = Field(default="New Model", max_length=50)
    company: str = Field(default="Unknown Company", max_length=50)


class Models(ModelBase, table=True):
    id: int | None = Field(default=None, primary_key=True)
