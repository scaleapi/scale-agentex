import contextvars
import logging
import os
import sys
from collections.abc import Sequence

import ddtrace
import json_log_formatter
from ddtrace.trace import tracer

# Check if Datadog is configured
_is_datadog_configured = bool(os.environ.get("DD_AGENT_HOST"))

# Include Datadog trace IDs only when Datadog is configured
if _is_datadog_configured:
    LOG_FORMAT: str = (
        "%(asctime)s %(levelname)s [%(name)s] [%(filename)s:%(lineno)d] "
        "[dd.trace_id=%(dd_trace_id)s dd.span_id=%(dd_span_id)s] - %(message)s"
    )
else:
    LOG_FORMAT: str = (
        "%(asctime)s %(levelname)s [%(name)s] [%(filename)s:%(lineno)d] - %(message)s"
    )

__all__: Sequence[str] = ("make_logger", "LOG_FORMAT")

ctx_var_request_id = contextvars.ContextVar[str]("request_id")


class CustomJSONFormatter(json_log_formatter.JSONFormatter):
    def json_record(self, message: str, extra: dict, record: logging.LogRecord) -> dict:
        extra = super().json_record(message, extra, record)
        extra["level"] = record.levelname
        extra["name"] = record.name
        extra["lineno"] = record.lineno
        extra["pathname"] = record.pathname

        # # add the http request id if it exists
        request_id = ctx_var_request_id.get(None)
        if request_id:
            extra["request_id"] = request_id

        if _is_datadog_configured:
            extra["dd.trace_id"] = tracer.get_log_correlation_context().get(
                "dd.trace_id", None
            ) or getattr(record, "dd.trace_id", 0)
            extra["dd.span_id"] = tracer.get_log_correlation_context().get(
                "dd.span_id", None
            ) or getattr(record, "dd.span_id", 0)
        # add the env, service, and version configured for the tracer.
        # If tracing is not set up, then this should pull values from DD_ENV, DD_SERVICE, and DD_VERSION.
        service_override = ddtrace.config.service or os.getenv("DD_SERVICE")
        if service_override:
            extra["dd.service"] = service_override

        env_override = ddtrace.config.env or os.getenv("DD_ENV")
        if env_override:
            extra["dd.env"] = env_override

        version_override = ddtrace.config.version or os.getenv("DD_VERSION")
        if version_override:
            extra["dd.version"] = version_override

        return extra


def make_logger(name: str) -> logging.Logger:
    log_level = logging.INFO

    if name is None or not isinstance(name, str) or len(name) == 0:
        raise ValueError("Name must be a non-empty string.")

    logger = logging.getLogger(name)
    stream_handler = logging.StreamHandler()
    if _is_datadog_configured:
        stream_handler.setFormatter(CustomJSONFormatter())
    else:
        stream_handler.setFormatter(logging.Formatter(LOG_FORMAT))

    logger.addHandler(stream_handler)
    logger.setLevel(log_level)

    def handle_exception(exc_type, exc_value, exc_traceback):
        if issubclass(exc_type, KeyboardInterrupt):
            sys.__excepthook__(exc_type, exc_value, exc_traceback)
            return

        logger.error(
            "Uncaught exception", exc_info=(exc_type, exc_value, exc_traceback)
        )

    sys.excepthook = handle_exception
    return logger
