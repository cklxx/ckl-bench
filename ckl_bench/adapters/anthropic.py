from __future__ import annotations

import json
import os
from typing import Any

from ckl_bench.core.usage import normalize_usage

from ._http import request_json
from .base import GenerateRequest, GenerateResponse


class AnthropicAdapter:
    """Adapter for Anthropic's Messages API."""

    name = "anthropic"

    def __init__(self, config: dict[str, Any]):
        self.base_url = (
            config.get("base_url")
            or os.environ.get("ANTHROPIC_BASE_URL")
            or "https://api.anthropic.com"
        ).rstrip("/")
        api_key = (
            config.get("api_key")
            or os.environ.get(config.get("api_key_env", ""))
            or os.environ.get("ANTHROPIC_API_KEY")
        )
        if not api_key:
            raise ValueError("anthropic adapter requires ANTHROPIC_API_KEY or config key 'api_key'")
        self.api_key = str(api_key)
        model = str(config.get("model") or "") or os.environ.get("ANTHROPIC_MODEL")
        if not model:
            raise ValueError("anthropic adapter requires --model or ANTHROPIC_MODEL")
        self.model = model
        self.temperature = float(config.get("temperature", 0))
        self.max_tokens = int(config.get("max_tokens", 512))
        self.version = config.get("anthropic_version", "2023-06-01")
        self.trusted_local = bool(config.get("trusted_local", False))

    def generate(self, request: GenerateRequest) -> GenerateResponse:
        system_parts: list[str] = []
        messages: list[dict[str, Any]] = []
        for message in request.messages:
            role = message["role"]
            content = message["content"]
            if role == "system":
                system_parts.append(content)
            else:
                messages.append(
                    {
                        "role": "assistant" if role == "assistant" else "user",
                        "content": [{"type": "text", "text": content}],
                    }
                )
        payload: dict[str, Any] = {
            "model": self.model,
            "messages": messages,
            "max_tokens": self.max_tokens,
            "temperature": self.temperature,
        }
        if system_parts:
            payload["system"] = "\n\n".join(system_parts)

        data = request_json(
            f"{self.base_url}/v1/messages",
            data=json.dumps(payload).encode("utf-8"),
            headers={
                "anthropic-version": self.version,
                "content-type": "application/json",
                "x-api-key": self.api_key,
            },
            timeout=request.timeout_s or 120,
            api_label="Anthropic API",
            trusted_local=self.trusted_local,
        )
        text = "".join(
            part.get("text", "")
            for part in data.get("content", [])
            if isinstance(part, dict) and part.get("type") == "text"
        )
        return GenerateResponse(
            text=text,
            raw=data,
            metadata={"model": self.model, "usage": normalize_usage(data).as_dict()},
        )
