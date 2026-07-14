from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from ckl_bench.core.cache import NullCache, ResponseCache, cache_key


class CacheTests(unittest.TestCase):
    def test_key_is_order_independent(self) -> None:
        a = cache_key({"model": "m", "messages": [1, 2], "temp": 0})
        b = cache_key({"temp": 0, "messages": [1, 2], "model": "m"})
        self.assertEqual(a, b)

    def test_key_changes_with_content(self) -> None:
        a = cache_key({"model": "m", "prompt": "x"})
        b = cache_key({"model": "m", "prompt": "y"})
        self.assertNotEqual(a, b)

    def test_roundtrip(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            cache = ResponseCache(Path(tmp))
            key = cache_key({"prompt": "hi"})
            self.assertIsNone(cache.get(key))
            cache.put(key, {"text": "hello", "usage": {"total_tokens": 3}})
            got = cache.get(key)
            self.assertIsNotNone(got)
            assert got is not None
            self.assertEqual(got["text"], "hello")

    def test_corrupt_entry_is_a_miss(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            cache = ResponseCache(Path(tmp))
            key = cache_key({"prompt": "hi"})
            path = cache.directory / key[:2] / f"{key}.json"
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text("{not json", encoding="utf-8")
            self.assertIsNone(cache.get(key))

    def test_null_cache_never_hits(self) -> None:
        cache = NullCache()
        key = cache_key({"prompt": "hi"})
        cache.put(key, {"text": "hello"})
        self.assertIsNone(cache.get(key))


if __name__ == "__main__":
    unittest.main()
