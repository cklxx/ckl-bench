from __future__ import annotations

import json
import unittest
from unittest.mock import patch

from ckl_bench.adapters.anthropic import AnthropicAdapter
from ckl_bench.adapters.base import GenerateRequest


class AnthropicAdapterTests(unittest.TestCase):
    def test_default_payload_omits_temperature(self) -> None:
        adapter = AnthropicAdapter({"api_key": "test", "model": "claude-opus-4-8"})
        self.assertIsNone(adapter.temperature)
        with patch(
            "ckl_bench.adapters.anthropic.request_json",
            return_value={"content": [], "usage": {}},
        ) as request_json:
            adapter.generate(GenerateRequest(case_id="case", prompt="hi", messages=[{"role": "user", "content": "hi"}]))
        payload = json.loads(request_json.call_args.kwargs["data"])
        self.assertNotIn("temperature", payload)

    def test_explicit_temperature_is_preserved(self) -> None:
        adapter = AnthropicAdapter(
            {"api_key": "test", "model": "legacy-model", "temperature": 0.25}
        )
        with patch(
            "ckl_bench.adapters.anthropic.request_json",
            return_value={"content": [], "usage": {}},
        ) as request_json:
            adapter.generate(GenerateRequest(case_id="case", prompt="hi", messages=[{"role": "user", "content": "hi"}]))
        payload = json.loads(request_json.call_args.kwargs["data"])
        self.assertEqual(payload["temperature"], 0.25)


if __name__ == "__main__":
    unittest.main()
