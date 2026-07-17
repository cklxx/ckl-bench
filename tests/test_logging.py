"""Tests for the aggregated, async logging subsystem."""

from __future__ import annotations

import logging
import tempfile
import unittest
from io import StringIO
from pathlib import Path

from ckl_bench.core.logging_config import (
    AggregatingHandler,
    setup_logging,
    shutdown_logging,
)


class AggregatingHandlerTests(unittest.TestCase):
    def setUp(self) -> None:
        self.stream = StringIO()
        self.inner = logging.StreamHandler(self.stream)
        self.inner.setFormatter(logging.Formatter("%(levelname)s %(message)s"))
        self.handler = AggregatingHandler(self.inner)

    def tearDown(self) -> None:
        self.handler.close()

    def _log(self, msg: str, level: int = logging.INFO, name: str = "test") -> None:
        record = logging.LogRecord(
            name=name, level=level, pathname="", lineno=0,
            msg=msg, args=(), exc_info=None,
        )
        self.handler.emit(record)

    def test_unique_messages_pass_through(self) -> None:
        self._log("first")
        self._log("second")
        self.handler.flush()
        out = self.stream.getvalue()
        self.assertIn("INFO first", out)
        self.assertIn("INFO second", out)
        self.assertNotIn("repeated", out)

    def test_consecutive_duplicates_collapsed(self) -> None:
        self._log("starting")
        self._log("starting")
        self._log("starting")
        self._log("done")
        self.handler.flush()
        out = self.stream.getvalue()
        # "starting" appears once annotated with the repeat count.
        self.assertEqual(out.count("starting"), 1)
        self.assertIn("(repeated 3x)", out)
        self.assertIn("INFO done", out)

    def test_different_levels_not_aggregated(self) -> None:
        self._log("same text", level=logging.INFO)
        self._log("same text", level=logging.WARNING)
        self.handler.flush()
        out = self.stream.getvalue()
        self.assertIn("INFO same text", out)
        self.assertIn("WARNING same text", out)
        self.assertNotIn("repeated", out)

    def test_different_loggers_not_aggregated(self) -> None:
        self._log("same text", name="a")
        self._log("same text", name="b")
        self.handler.flush()
        out = self.stream.getvalue()
        self.assertEqual(out.count("same text"), 2)
        self.assertNotIn("repeated", out)

    def test_flush_emits_pending(self) -> None:
        self._log("pending")
        self._log("pending")
        # Before flush, nothing should have been written (still buffering).
        self.assertEqual(self.stream.getvalue(), "")
        self.handler.flush()
        self.assertIn("(repeated 2x)", self.stream.getvalue())


class SetupLoggingTests(unittest.TestCase):
    def tearDown(self) -> None:
        shutdown_logging()

    def test_setup_logging_writes_to_file_async(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            log_path = Path(tmp) / "test.log"
            setup_logging(level=logging.INFO, log_file=log_path, console=False)
            logger = logging.getLogger("ckl.test.async")
            logger.info("hello file")
            # Flush the async queue.
            shutdown_logging()
            content = log_path.read_text(encoding="utf-8")
            self.assertIn("hello file", content)

    def test_setup_logging_is_idempotent(self) -> None:
        setup_logging(level=logging.INFO, console=True)
        setup_logging(level=logging.DEBUG, console=True)  # second call ignored
        root = logging.getLogger()
        # Only one QueueHandler added.
        from logging.handlers import QueueHandler
        queue_handlers = [h for h in root.handlers if isinstance(h, QueueHandler)]
        self.assertEqual(len(queue_handlers), 1)


if __name__ == "__main__":
    unittest.main()
