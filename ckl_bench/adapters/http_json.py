from __future__ import annotations

import json
import os
from typing import Any

from ckl_bench.core.usage import normalize_usage

from ._http import request_json
from .base import GenerateRequest, GenerateResponse


def _extract_path(data: Any, path: str) -> Any:
    current = data
    for part in path.split("."):
        if isinstance(current, list):
            current = current[int(part)]
        elif isinstance(current, dict):
            current = current[part]
        else:
            raise KeyError(path)
    return current


class HTTPJsonAdapter:
    """Generic POST adapter for APIs that accept JSON and return JSON."""

    name = "http-json"

    def __init__(self, config: dict[str, Any]):
        endpoint = config.get("endpoint")
        if not endpoint:
            raise ValueError("http-json adapter requires config key 'endpoint' or --endpoint")
        self.endpoint = endpoint
        self.model = config.get("model")
        self.headers = dict(config.get("headers", {}))
        self.timeout_s = float(config.get("timeout_s", 120))
        self.text_path = config.get("text_path")
        self.trusted_local = bool(config.get("trusted_local", False))

        api_key = config.get("api_key")
        if not api_key and config.get("api_key_env"):
            api_key = os.environ.get(config["api_key_env"])
        if api_key:
            header = config.get("auth_header", "Authorization")
            prefix = config.get("auth_prefix", "Bearer ")
            self.headers[header] = f"{prefix}{api_key}"

    def generate(self, request: GenerateRequest) -> GenerateResponse:
        payload = {
            "model": self.model,
            "messages": request.messages,
            "prompt": request.prompt,
            "case_id": request.case_id,
            "metadata": request.metadata,
        }
        body = json.dumps(payload).encode("utf-8")
        headers = {"Content-Type": "application/json", **self.headers}
        timeout = request.timeout_s or self.timeout_s
        data = request_json(
            self.endpoint,
            data=body,
            headers=headers,
            timeout=timeout,
            api_label=self.endpoint,
            trusted_local=self.trusted_local,
        )
        meta = {"usage": normalize_usage(data).as_dict()}
        if self.text_path:
            text = _extract_path(data, self.text_path)
            return GenerateResponse(text=str(text), raw=data, metadata=meta)
        for path in ("choices.0.message.content", "text", "response", "output", "answer"):
            try:
                text = _extract_path(data, path)
                if isinstance(text, str):
                    return GenerateResponse(text=text, raw=data, metadata=meta)
            except (KeyError, IndexError, ValueError, TypeError):
                continue
        return GenerateResponse(text=json.dumps(data), raw=data, metadata=meta)
