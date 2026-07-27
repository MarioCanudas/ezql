from pydantic import BaseModel, ConfigDict, Field
from backend.models.blocks import AgentResponse, UIBlock, FlexibleDataBlock
from backend.models.metadata import MessageMetadata


class AgentReply(BaseModel):
    model_config = ConfigDict(frozen=True)

    text: str
    response: AgentResponse | None = None
    blocks: list[UIBlock] | None = None
    data: list[FlexibleDataBlock] | None = None
    metadata: MessageMetadata = Field(default_factory=dict)
