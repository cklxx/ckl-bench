from __future__ import annotations

import json
import os
from typing import Any

from ckl_bench.core.usage import normalize_usage

from ._http import request_json
from .base import GenerateRequest, GenerateResponse


class OpenAICompatibleAdapter:
    """Adapter for OpenAI-compatible chat completions APIs."""

    name = "openai"

    def __init__(self, config: dict[str, Any]):
        self.base_url = (
            config.get("base_url")
            or os.environ.get("CKL_OPENAI_BASE_URL")
            or os.environ.get("OPENAI_BASE_URL")
            or "https://api.openai.com/v1"
        ).rstrip("/")
        api_key_env = config.get("api_key_env")
        api_key_envs = config.get("api_key_envs")
        if config.get("api_key"):
            self.api_key = config["api_key"]
        elif isinstance(api_key_envs, list):
            self.api_key = next((os.environ.get(name) for name in api_key_envs if os.environ.get(name)), None)
        elif api_key_env:
            self.api_key = os.environ.get(api_key_env)
        else:
            self.api_key = os.environ.get("CKL_OPENAI_API_KEY") or os.environ.get("OPENAI_API_KEY")
        if not self.api_key:
            raise ValueError(
                "openai adapter requires OPENAI_API_KEY, CKL_OPENAI_API_KEY, "
                "or config key 'api_key'"
            )
        self.model = config.get("model") or os.environ.get("CKL_MODEL")
        if not self.model:
            raise ValueError("openai adapter requires --model or CKL_MODEL")
        self.temperature = float(config.get("temperature", 0))
        self.max_tokens = config.get("max_tokens")
        self.extra_body = dict(config.get("extra_body", {}))
        self.trusted_local = bool(config.get("trusted_local", False))

    def generate(self, request: GenerateRequest) -> GenerateResponse:
        payload: dict[str, Any] = {
            "model": self.model,
            "messages": request.messages,
            "temperature": self.temperature,
            **self.extra_body,
        }
        if self.max_tokens is not None:
            payload["max_tokens"] = int(self.max_tokens)
        body = json.dumps(payload).encode("utf-8")
        data = request_json(
            f"{self.base_url}/chat/completions",
            data=body,
            headers={
                "Authorization": f"Bearer {self.api_key}",
                "Content-Type": "application/json",
            },
            timeout=request.timeout_s or 120,
            api_label="OpenAI-compatible API",
            trusted_local=self.trusted_local,
        )
        text = data["choices"][0]["message"].get("content") or ""
        return GenerateResponse(
            text=text,
            raw=data,
            metadata={"model": self.model, "usage": normalize_usage(data).as_dict()},
        )
