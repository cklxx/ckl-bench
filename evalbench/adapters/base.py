from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Protocol


@dataclass(frozen=True)
class GenerateRequest:
    case_id: str
    messages: list[dict[str, str]]
    prompt: str
    workspace_path: Path | None = None
    metadata: dict[str, Any] = field(default_factory=dict)
    timeout_s: float | None = None


@dataclass
class GenerateResponse:
    text: str
    raw: Any = None
    metadata: dict[str, Any] = field(default_factory=dict)


class ModelAdapter(Protocol):
    name: str

    def generate(self, request: GenerateRequest) -> GenerateResponse:
        """Return one model or agent response for a case."""
