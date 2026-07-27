from __future__ import annotations

from pydantic import BaseModel, JsonValue


class MetadataValue(BaseModel):
    """A displayable fact with traceable tool provenance."""

    value: JsonValue
    display: str
    artifact_id: str
    path: str
    label: str | None = None
    presentation_type: str | None = None


MessageMetadata = dict[str, MetadataValue]
