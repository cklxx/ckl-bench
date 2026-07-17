"""Unified logging setup with aggregation and async file writing.

Two improvements over bare ``logging.basicConfig``:

* **Aggregation** — consecutive identical log lines are collapsed into a
  single line annotated with a repeat count, so a run of 100 identical
  "case started" messages becomes one line.  This keeps the dashboard
  server console readable during long runs.
* **Async file writing** — log records are handed off to a background
  thread via :class:`logging.handlers.QueueHandler` /
  :class:`~logging.handlers.QueueListener`, so file I/O never blocks the
  run threads or the HTTP/WebSocket event loop.

Usage::

    from ckl_bench.core.logging_config import setup_logging, shutdown_logging

    setup_logging(log_file="runs/server.log")
    ...
    shutdown_logging()  # flush and stop the background writer

``setup_logging`` is idempotent — only the first call takes effect, so it
is safe to call from multiple entry points.
"""

from __future__ import annotations

import atexit
import logging
import logging.handlers
import queue
import threading
from pathlib import Path

DEFAULT_FORMAT = "%(asctime)s %(levelname)s %(name)s: %(message)s"
DEFAULT_DATEFMT = "%H:%M:%S"

#: Module-level log file path shared by the CLI and server so the daemon
#: subprocess can inherit the same destination.
LOG_FILE_ENV = "CKL_LOG_FILE"

_lock = threading.Lock()
_configured = False
_listener: logging.handlers.QueueListener | None = None
_queue_handler: logging.handlers.QueueHandler | None = None


class AggregatingHandler(logging.Handler):
    """Collapse consecutive identical log records into one.

    When the same message (same logger, level, and text) is emitted N
    times in a row, only the first occurrence is forwarded to the wrapped
    handler immediately; the repetitions are held back and emitted as
    ``<msg> ... (repeated Nx)`` once a different message arrives or the
    handler is flushed/closed.

    This wraps another handler (typically a ``StreamHandler``), so
    aggregation is transparent to formatting and output destination.
    """

    def __init__(self, handler: logging.Handler) -> None:
        super().__init__()
        self._handler = handler
        self._last_key: tuple[str, int, str] | None = None
        self._last_record: logging.LogRecord | None = None
        self._repeat_count = 0
        self._agg_lock = threading.Lock()

    def emit(self, record: logging.LogRecord) -> None:
        key = (record.name, record.levelno, record.getMessage())
        with self._agg_lock:
            if key == self._last_key:
                self._repeat_count += 1
                return
            self._flush_locked()
            self._last_key = key
            self._last_record = record
            self._repeat_count = 1

    def _flush_locked(self) -> None:
        if self._last_record is None:
            return
        record = self._last_record
        if self._repeat_count > 1:
            # Clone the record and annotate its message with the repeat
            # count.  ``args`` is cleared so ``getMessage`` returns the
            # rewritten ``msg`` verbatim.
            attrs = self._last_record.__dict__.copy()
            attrs["msg"] = f"{self._last_key[2]} ... (repeated {self._repeat_count}x)"
            attrs["args"] = None
            record = logging.makeLogRecord(attrs)
        self._handler.emit(record)
        self._last_key = None
        self._last_record = None
        self._repeat_count = 0

    def flush(self) -> None:
        with self._agg_lock:
            self._flush_locked()
        self._handler.flush()

    def close(self) -> None:
        self.flush()
        self._handler.close()
        super().close()


def setup_logging(
    level: int = logging.INFO,
    log_file: str | Path | None = None,
    console: bool = True,
) -> None:
    """Configure the root logger.  Idempotent — only the first call applies.

    Parameters
    ----------
    level:
        Minimum level to process.
    log_file:
        If given, write logs to this file asynchronously (rotating,
        5 MB x 3 backups).
    console:
        Whether to mirror logs to the console with aggregation.
    """
    global _configured, _listener
    with _lock:
        if _configured:
            return
        _configured = True

    root = logging.getLogger()
    root.setLevel(level)
    formatter = logging.Formatter(DEFAULT_FORMAT, datefmt=DEFAULT_DATEFMT)

    handlers: list[logging.Handler] = []

    if console:
        stream_handler = logging.StreamHandler()
        stream_handler.setFormatter(formatter)
        handlers.append(AggregatingHandler(stream_handler))

    if log_file is not None:
        file_handler = logging.handlers.RotatingFileHandler(
            str(log_file), maxBytes=5_000_000, backupCount=3, encoding="utf-8"
        )
        file_handler.setFormatter(formatter)
        handlers.append(file_handler)

    if not handlers:
        return

    # Async hand-off: a single QueueHandler on the root logger feeds a
    # background-thread QueueListener that fans out to the real handlers.
    # This keeps all file I/O off the run threads and the HTTP/WebSocket
    # event loop.
    global _queue_handler
    queue_handler = logging.handlers.QueueHandler(queue.Queue(-1))
    root.addHandler(queue_handler)
    _queue_handler = queue_handler
    _listener = logging.handlers.QueueListener(
        queue_handler.queue, *handlers, respect_handler_level=True
    )
    _listener.start()
    atexit.register(shutdown_logging)


def shutdown_logging() -> None:
    """Flush pending records and stop the background writer thread.

    Reverses :func:`setup_logging` so logging can be reconfigured (e.g. in
    tests).  Does not call ``logging.shutdown`` — that is a process-exit
    only operation that would permanently disable the root logger.
    """
    global _listener, _configured, _queue_handler
    with _lock:
        if _listener is not None:
            _listener.stop()
            _listener = None
        if _queue_handler is not None:
            logging.getLogger().removeHandler(_queue_handler)
            _queue_handler = None
        _configured = False
