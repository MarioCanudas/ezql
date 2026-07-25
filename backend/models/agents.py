from pydantic import BaseModel, ConfigDict
from backend.models.blocks import AgentResponse, UIBlock, FlexibleDataBlock


class AgentReply(BaseModel):
    model_config = ConfigDict(frozen=True)

    text: str
    response: AgentResponse | None = None
    blocks: list[UIBlock] | None = None
    data: list[FlexibleDataBlock] | None = None
