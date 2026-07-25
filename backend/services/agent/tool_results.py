from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field


class ToolResult(BaseModel):
    """Stable, model-facing result returned by every agent tool."""

    ok: bool
    summary: str
    data: Any = None
    warnings: list[str] = Field(default_factory=list)


def tool_success(
    summary: str,
    *,
    data: Any = None,
    warnings: list[str] | None = None,
) -> dict[str, Any]:
    return ToolResult(
        ok=True,
        summary=summary,
        data=data,
        warnings=warnings or [],
    ).model_dump()


def tool_failure(summary: str) -> dict[str, Any]:
    """Return a business-safe failure without leaking implementation details."""
    return ToolResult(ok=False, summary=summary).model_dump()
