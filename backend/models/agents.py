from typing import Any
from pydantic import BaseModel, ConfigDict
from backend.models.blocks import FlexibleDataBlock


class AgentReply(BaseModel):
    model_config = ConfigDict(frozen=True)

    text: str
    data: list[FlexibleDataBlock] | None = None
