from __future__ import annotations

import re
from typing import Any

from backend.models.blocks import UIBlock
from backend.models.metadata import MessageMetadata, MetadataValue
from backend.services.agent.state import PresentationCandidate, ToolArtifact
from pydantic import TypeAdapter

MISSING_VALUE = "Dato no disponible"
_REFERENCE_PATTERN = re.compile(r"\{\{meta\.([A-Za-z0-9_.-]+)\}\}")


def _safe_segment(value: object) -> str:
    return re.sub(r"[^A-Za-z0-9_-]", "_", str(value))


def build_artifact_metadata(artifact_id: str, data: Any) -> MessageMetadata:
    """Flatten scalar output for internal debugging, never for presentation."""
    metadata: MessageMetadata = {}

    def visit(value: Any, path: list[str]) -> None:
        if isinstance(value, dict):
            for key, nested in value.items():
                visit(nested, [*path, _safe_segment(key)])
        elif isinstance(value, list):
            for index, nested in enumerate(value):
                visit(nested, [*path, str(index)])
        elif isinstance(value, (str, int, float, bool)) and not isinstance(value, bool):
            key = ".".join([_safe_segment(artifact_id), *path])
            metadata[key] = MetadataValue(
                value=value,
                display=str(value),
                artifact_id=artifact_id,
                path=".".join(path),
            )

    visit(data, ["data"])
    return metadata


def state_metadata(artifacts: list[ToolArtifact]) -> MessageMetadata:
    metadata: MessageMetadata = {}
    for artifact in artifacts:
        if artifact.ok:
            metadata.update(artifact.metadata)
    return metadata


def presentation_catalog(
    artifact_id: str, data: Any
) -> tuple[MessageMetadata, list[PresentationCandidate]]:
    """Build a small, semantic catalog from tool-proposed presentation blocks."""
    if not isinstance(data, dict):
        return {}, []

    adapter = TypeAdapter(UIBlock)
    metadata: MessageMetadata = {}
    candidates: list[PresentationCandidate] = []
    for index, raw_block in enumerate(data.get("suggested_blocks", [])):
        try:
            block = adapter.validate_python(raw_block)
        except Exception:
            continue
        candidate_id = f"{artifact_id}.block.{index}"
        fact_keys: list[str] = []
        if block.type == "metric":
            payload = block.model_dump()
            key = f"{artifact_id}.fact.{_safe_segment(block.label)}.{index}"
            metadata[key] = MetadataValue(
                value=block.value,
                display=block.value,
                artifact_id=artifact_id,
                path=f"data.suggested_blocks.{index}.value",
                label=block.label,
                presentation_type="metric",
            )
            payload["value"] = metadata_reference(key)
            fact_keys.append(key)
            if block.delta is not None:
                delta_key = f"{artifact_id}.fact.{_safe_segment(block.label)}_delta.{index}"
                metadata[delta_key] = MetadataValue(
                    value=block.delta,
                    display=block.delta,
                    artifact_id=artifact_id,
                    path=f"data.suggested_blocks.{index}.delta",
                    label=f"Variación de {block.label}",
                    presentation_type="metric_delta",
                )
                payload["delta"] = metadata_reference(delta_key)
                fact_keys.append(delta_key)
            block = adapter.validate_python(payload)
        candidates.append(PresentationCandidate(
            id=candidate_id, tool_call_id=artifact_id, block=block, fact_keys=fact_keys
        ))

    chart = data.get("chart")
    if isinstance(chart, dict):
        try:
            candidates.append(PresentationCandidate(
                id=f"{artifact_id}.chart",
                tool_call_id=artifact_id,
                block=adapter.validate_python(chart),
            ))
        except Exception:
            pass
    return metadata, candidates


def state_candidates(artifacts: list[ToolArtifact]) -> list[PresentationCandidate]:
    return [candidate for artifact in artifacts if artifact.ok for candidate in artifact.presentation_candidates]


def template_is_safe(template: str, metadata: MessageMetadata) -> bool:
    return all(reference in metadata for reference in _REFERENCE_PATTERN.findall(template))


def safe_template(template: str, metadata: MessageMetadata, *, fallback: str = MISSING_VALUE) -> str:
    def replace(match: re.Match[str]) -> str:
        return match.group(0) if match.group(1) in metadata else fallback
    return _REFERENCE_PATTERN.sub(replace, template)


def sanitize_generated_block(block: UIBlock, metadata: MessageMetadata) -> UIBlock:
    """Prevent model-created numbers or invalid references from reaching the UI."""
    payload = block.model_dump()
    if payload["type"] == "markdown":
        payload["content"] = safe_template(payload["content"], metadata)
    elif payload["type"] == "metric":
        payload["value"] = safe_template(payload["value"], metadata)
        if payload.get("delta") is not None and not template_is_safe(payload["delta"], metadata):
            payload["delta"] = None
    return TypeAdapter(UIBlock).validate_python(payload)


def metadata_reference(key: str) -> str:
    return "{{meta." + key + "}}"
