from __future__ import annotations

import json
import os
import urllib.parse
from typing import Any

from ckl_bench.core.usage import normalize_usage

from ._http import request_json
from .base import GenerateRequest, GenerateResponse


class GeminiAdapter:
    """Adapter for Google Gemini's generateContent API."""

    name = "gemini"

    def __init__(self, config: dict[str, Any]):
        self.base_url = (
            config.get("base_url")
            or os.environ.get("GEMINI_BASE_URL")
            or "https://generativelanguage.googleapis.com/v1beta"
        ).rstrip("/")
        api_key = (
            config.get("api_key")
            or os.environ.get(config.get("api_key_env", ""))
            or os.environ.get("GEMINI_API_KEY")
            or os.environ.get("GOOGLE_API_KEY")
        )
        if not api_key:
            raise ValueError("gemini adapter requires GEMINI_API_KEY, GOOGLE_API_KEY, or config key 'api_key'")
        self.api_key = str(api_key)
        model = str(config.get("model") or "") or os.environ.get("GEMINI_MODEL")
        if not model:
            raise ValueError("gemini adapter requires --model or GEMINI_MODEL")
        self.model = model
        self.temperature = float(config.get("temperature", 0))
        self.max_tokens = config.get("max_tokens")
        self.trusted_local = bool(config.get("trusted_local", False))

    def generate(self, request: GenerateRequest) -> GenerateResponse:
        contents: list[dict[str, Any]] = []
        system_parts: list[dict[str, str]] = []
        for message in request.messages:
            role = message["role"]
            part = {"text": message["content"]}
            if role == "system":
                system_parts.append(part)
            else:
                contents.append(
                    {
                        "role": "model" if role == "assistant" else "user",
                        "parts": [part],
                    }
                )

        payload: dict[str, Any] = {
            "contents": contents,
            "generationConfig": {"temperature": self.temperature},
        }
        if system_parts:
            payload["systemInstruction"] = {"parts": system_parts}
        if self.max_tokens is not None:
            payload["generationConfig"]["maxOutputTokens"] = int(self.max_tokens)

        model = urllib.parse.quote(self.model, safe="")
        data = request_json(
            f"{self.base_url}/models/{model}:generateContent",
            data=json.dumps(payload).encode("utf-8"),
            headers={
                "content-type": "application/json",
                "x-goog-api-key": self.api_key,
            },
            timeout=request.timeout_s or 120,
            api_label="Gemini API",
            trusted_local=self.trusted_local,
        )
        parts = data["candidates"][0]["content"].get("parts", [])
        text = "".join(part.get("text", "") for part in parts if isinstance(part, dict))
        return GenerateResponse(
            text=text,
            raw=data,
            metadata={"model": self.model, "usage": normalize_usage(data).as_dict()},
        )
