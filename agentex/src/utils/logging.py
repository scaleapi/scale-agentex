import contextvars
import logging
import os
import re
import sys
from collections.abc import Sequence

import ddtrace
import json_log_formatter
from ddtrace.trace import tracer

from src.utils.request_utils import REQUEST_KEY_REGEXP_BLACKLIST

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

# Defense in depth against credential leaks in logs. Even though no code path
# should log a secret directly, objects like the request principal context can
# carry an ``api_key`` and may end up interpolated into a log message (via %s or
# an f-string). This filter masks the *value* that follows any sensitive key
# name in the rendered message, so a credential never reaches log aggregation.
#
# Key names reuse REQUEST_KEY_REGEXP_BLACKLIST (the request-body scrubber's list)
# so the two stay in sync. The pattern matches common renderings — dict repr
# (``'api_key': 'x'``), kwargs/model repr (``api_key='x'``) and JSON
# (``"api_key": "x"``) — preserving the surrounding quote style.
#
# The value sub-pattern also absorbs an optional auth-scheme prefix
# (``Bearer``/``Basic``/...) so ``Authorization: Bearer <token>`` redacts the
# whole credential rather than stopping at the first space. It deliberately
# matches only the scheme word plus a single token (not the rest of the line),
# so an unquoted tail like ``token: foo bar baz`` masks just ``foo``.
_AUTH_SCHEME = r"(?:bearer|basic|digest|token)\s+"
_SENSITIVE_VALUE_RE = re.compile(
    r"(?P<key>" + "|".join(REQUEST_KEY_REGEXP_BLACKLIST) + r")"
    r"(?P<sep>['\"]?\s*[:=]\s*)"
    r"(?P<quote>['\"]?)"
    r"(?P<value>" + _AUTH_SCHEME + r"[^\s'\"},]+|[^\s'\"},]+)"
    r"(?P=quote)",
    re.IGNORECASE,
)
_REDACTION_TEMPLATE = r"\g<key>\g<sep>\g<quote>[REDACTED]\g<quote>"


def redact_sensitive_text(message: str) -> str:
    """Mask secret values that follow a sensitive key name in ``message``."""
    return _SENSITIVE_VALUE_RE.sub(_REDACTION_TEMPLATE, message)


class SensitiveDataFilter(logging.Filter):
    """Redact secret values (api keys, tokens, cookies, ...) from log messages.

    Runs on every record emitted through a ``make_logger`` handler. It rewrites
    the fully-rendered message (after %-args/f-string interpolation) so that even
    an accidental ``logger.info("... %s", principal_context)`` cannot emit a raw
    credential. Note: this scrubs the message text only — values passed via
    ``extra={...}`` structured fields are out of scope and should already use
    non-sensitive identifiers (e.g. ``api_key_id``, not the key itself).
    """

    def filter(self, record: logging.LogRecord) -> bool:
        try:
            message = record.getMessage()
        except Exception:
            # Never let redaction break logging itself.
            return True
        redacted = redact_sensitive_text(message)
        if redacted != message:
            record.msg = redacted
            record.args = ()
        return True


_sensitive_data_filter = SensitiveDataFilter()


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

    # Mask secret values before any handler emits the record. Attaching to the
    # logger (not the handler) means the redaction runs once, up front, and
    # applies to every downstream handler the record propagates to.
    if _sensitive_data_filter not in logger.filters:
        logger.addFilter(_sensitive_data_filter)

    def handle_exception(exc_type, exc_value, exc_traceback):
        if issubclass(exc_type, KeyboardInterrupt):
            sys.__excepthook__(exc_type, exc_value, exc_traceback)
            return

        logger.error(
            "Uncaught exception", exc_info=(exc_type, exc_value, exc_traceback)
        )

    sys.excepthook = handle_exception
    return logger
