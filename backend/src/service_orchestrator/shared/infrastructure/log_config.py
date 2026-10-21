from __future__ import annotations

import json
import logging
import sys
from contextvars import ContextVar
from datetime import UTC, datetime
from typing import Any, Final

request_id_var: ContextVar[str | None] = ContextVar("request_id", default=None)

_HANDLER_NAME: Final = "service_orchestrator"
_RESERVED: Final = frozenset(vars(logging.LogRecord("", 0, "", 0, "", (), None))) | {
    "message",
    "asctime",
    "request_id",
}
_base_record_factory = logging.getLogRecordFactory()


def _record_with_request_id(*args: Any, **kwargs: Any) -> logging.LogRecord:
    record = _base_record_factory(*args, **kwargs)
    record.request_id = request_id_var.get()
    return record


def extra_fields(record: logging.LogRecord) -> dict[str, Any]:
    return {key: value for key, value in vars(record).items() if key not in _RESERVED}


def _text_value(value: Any) -> str:
    if isinstance(value, str):
        return value if value and " " not in value else json.dumps(value)
    return json.dumps(value, default=str)


class TextFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        parts = [self.formatTime(record), f"{record.levelname:<7}", record.name]
        if request_id := getattr(record, "request_id", None):
            parts.append(f"[{request_id}]")
        parts.append(record.getMessage())
        parts.extend(f"{key}={_text_value(value)}" for key, value in extra_fields(record).items())
        line = " ".join(parts)
        if record.exc_info:
            line += "\n" + self.formatException(record.exc_info)
        return line


class JsonFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        document: dict[str, Any] = {
            "time": datetime.fromtimestamp(record.created, UTC).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
        }
        if request_id := getattr(record, "request_id", None):
            document["request_id"] = request_id
        document.update(extra_fields(record))
        if record.exc_info:
            document["exception"] = self.formatException(record.exc_info)
        return json.dumps(document, default=str)


def configure_logging(level: str = "INFO", fmt: str = "text", log_sql: bool = False) -> None:
    logging.setLogRecordFactory(_record_with_request_id)
    handler = logging.StreamHandler(sys.stderr)
    handler.set_name(_HANDLER_NAME)
    handler.setFormatter(JsonFormatter() if fmt == "json" else TextFormatter())
    for name, logger_level in (
        ("service_orchestrator", level.upper()),
        ("sqlalchemy.engine", "INFO" if log_sql else "WARNING"),
    ):
        logger = logging.getLogger(name)
        for existing in [h for h in logger.handlers if h.get_name() == _HANDLER_NAME]:
            logger.removeHandler(existing)
        logger.addHandler(handler)
        logger.setLevel(logger_level)
