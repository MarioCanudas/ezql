from typing import Any
from pydantic import BaseModel, ConfigDict, Field
from backend.models.blocks import AgentResponse, UIBlock
from backend.models.metadata import MessageMetadata


class AgentReply(BaseModel):
    model_config = ConfigDict(frozen=True)

    text: str
    response: AgentResponse | None = None
    blocks: list[UIBlock] | None = None
    data: list[dict[str, Any]] | None = None
    metadata: MessageMetadata = Field(default_factory=dict)
