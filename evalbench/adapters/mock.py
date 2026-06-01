from __future__ import annotations

from typing import Any

from .base import GenerateRequest, GenerateResponse


class MockAdapter:
    """Deterministic adapter for smoke tests and case authoring."""

    name = "mock"

    def __init__(self, config: dict[str, Any]):
        self.responses = dict(config.get("responses", {}))
        self.default_response = config.get("default_response")
        self.echo = bool(config.get("echo", True))

    def generate(self, request: GenerateRequest) -> GenerateResponse:
        if request.case_id in self.responses:
            return GenerateResponse(text=str(self.responses[request.case_id]), raw={"source": "case_id"})
        if self.default_response is not None:
            return GenerateResponse(text=str(self.default_response), raw={"source": "default"})
        if self.echo:
            return GenerateResponse(text=request.prompt, raw={"source": "echo"})
        return GenerateResponse(text="", raw={"source": "empty"})
