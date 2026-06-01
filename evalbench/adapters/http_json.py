from __future__ import annotations

import json
import os
import urllib.error
import urllib.request
from typing import Any

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
        req = urllib.request.Request(self.endpoint, data=body, headers=headers, method="POST")
        timeout = request.timeout_s or self.timeout_s
        try:
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                raw_text = resp.read().decode("utf-8")
        except urllib.error.HTTPError as exc:
            detail = exc.read().decode("utf-8", errors="replace")
            raise RuntimeError(f"HTTP {exc.code} from {self.endpoint}: {detail}") from exc

        data = json.loads(raw_text)
        if self.text_path:
            text = _extract_path(data, self.text_path)
            return GenerateResponse(text=str(text), raw=data)
        for path in ("choices.0.message.content", "text", "response", "output", "answer"):
            try:
                text = _extract_path(data, path)
                if isinstance(text, str):
                    return GenerateResponse(text=text, raw=data)
            except (KeyError, IndexError, ValueError, TypeError):
                continue
        return GenerateResponse(text=raw_text, raw=data)
