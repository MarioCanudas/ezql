from __future__ import annotations

import json
import os
import subprocess
import time
from typing import Any, Protocol

from pydantic import BaseModel, Field, ValidationError

SANDBOX_IMAGE = os.getenv("EZQL_STATISTICS_SANDBOX_IMAGE", "ezql-statistics-sandbox:0.1.0")
SANDBOX_TIMEOUT_SECONDS = 8
MAX_SANDBOX_OUTPUT_BYTES = 64 * 1024


class SandboxResult(BaseModel):
    findings: list[str] = Field(default_factory=list, max_length=10)
    metrics: dict[str, float | int | str] = Field(default_factory=dict, max_length=12)
    tables: list[dict[str, Any]] = Field(default_factory=list, max_length=3)
    warnings: list[str] = Field(default_factory=list, max_length=10)


class SandboxExecutor(Protocol):
    def execute(self, *, code: str, records: list[dict[str, Any]]) -> tuple[SandboxResult, float]: ...


class DockerStatisticsSandbox:
    """Runs the prebuilt statistics runtime without host mounts, network, or privileges."""

    def execute(self, *, code: str, records: list[dict[str, Any]]) -> tuple[SandboxResult, float]:
        payload = json.dumps({"code": code, "records": records}, ensure_ascii=False).encode()
        command = [
            "docker", "run", "--rm", "--interactive", "--network", "none", "--read-only",
            "--tmpfs", "/tmp:rw,noexec,nosuid,size=16m", "--cap-drop", "ALL",
            "--security-opt", "no-new-privileges", "--pids-limit", "64", "--memory", "256m",
            "--cpus", "0.5", "--user", "65534:65534", SANDBOX_IMAGE,
        ]
        started = time.monotonic()
        try:
            completed = subprocess.run(
                command, input=payload, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
                timeout=SANDBOX_TIMEOUT_SECONDS, check=False,
            )
        except (OSError, subprocess.TimeoutExpired) as exc:
            raise RuntimeError("sandbox unavailable") from exc
        duration = time.monotonic() - started
        if completed.returncode != 0 or len(completed.stdout) > MAX_SANDBOX_OUTPUT_BYTES:
            raise RuntimeError("sandbox execution failed")
        try:
            return SandboxResult.model_validate_json(completed.stdout), duration
        except ValidationError as exc:
            raise RuntimeError("sandbox returned invalid evidence") from exc
