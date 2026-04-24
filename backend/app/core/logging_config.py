"""Structured JSON logging configuration.

Call configure_logging() once at startup.  After that, all stdlib loggers
emit newline-delimited JSON to stdout with fields:
  ts, level, logger, message, plus any extras passed via extra={}
"""
from __future__ import annotations

import json
import logging
import sys
import time


class _JsonFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        payload: dict = {
            "ts": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(record.created)),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
        }
        if record.exc_info:
            payload["exc"] = self.formatException(record.exc_info)
        # Forward any extra fields attached via extra={}
        skip = logging.LogRecord.__dict__.keys() | {
            "message", "asctime", "args", "exc_info", "exc_text", "stack_info",
            "lineno", "funcName", "pathname", "filename", "module", "msecs",
            "relativeCreated", "thread", "threadName", "processName", "process",
            "name", "levelno", "levelname", "created", "msg",
        }
        for k, v in record.__dict__.items():
            if k not in skip:
                payload[k] = v
        return json.dumps(payload, default=str)


def configure_logging(level: str = "INFO") -> None:
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(_JsonFormatter())
    root = logging.getLogger()
    root.handlers.clear()
    root.addHandler(handler)
    root.setLevel(getattr(logging, level.upper(), logging.INFO))
    # Quiet noisy libraries
    for noisy in ("uvicorn.access", "sqlalchemy.engine"):
        logging.getLogger(noisy).setLevel(logging.WARNING)
