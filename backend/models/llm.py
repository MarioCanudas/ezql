from pydantic import BaseModel, ConfigDict


class LLMProviderConfig(BaseModel):
    model_config = ConfigDict(frozen=True)

    name: str
    default_base_url: str | None = None
    base_url_env: str | None = None
