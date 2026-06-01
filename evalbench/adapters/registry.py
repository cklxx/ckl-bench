from __future__ import annotations

import importlib
from typing import Any

from .anthropic import AnthropicAdapter
from .command import CommandAdapter
from .gemini import GeminiAdapter
from .http_json import HTTPJsonAdapter
from .mock import MockAdapter
from .openai_compatible import OpenAICompatibleAdapter


BUILT_INS = {
    "anthropic": AnthropicAdapter,
    "command": CommandAdapter,
    "gemini": GeminiAdapter,
    "http-json": HTTPJsonAdapter,
    "mock": MockAdapter,
    "openai": OpenAICompatibleAdapter,
    "openai-compatible": OpenAICompatibleAdapter,
}


def build_adapter(name: str, config: dict[str, Any]):
    adapter_cls = BUILT_INS.get(name)
    if adapter_cls is None:
        if ":" not in name:
            known = ", ".join(sorted(BUILT_INS))
            raise ValueError(f"unknown adapter '{name}'. Built-ins: {known}")
        module_name, attr = name.split(":", 1)
        module = importlib.import_module(module_name)
        adapter_cls = getattr(module, attr)
    return adapter_cls(config)
