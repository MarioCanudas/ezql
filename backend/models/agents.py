from pydantic import BaseModel, ConfigDict, JsonValue


class AgentReply(BaseModel):
    model_config = ConfigDict(frozen=True)

    text: str
    data: list[dict[str, JsonValue]] | None = None
