import logging
import os
import sys
from collections.abc import Sequence

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


class DatadogLogFilter(logging.Filter):
    """
    Ensures dd_trace_id and dd_span_id exist on log records when Datadog is enabled.
    Only used when DD_AGENT_HOST is set.
    """

    def filter(self, record):
        # Set defaults if not present (safety for when DD_LOGS_INJECTION isn't true)
        if not hasattr(record, "dd_trace_id"):
            record.dd_trace_id = "0"
        if not hasattr(record, "dd_span_id"):
            record.dd_span_id = "0"
        return True


def make_logger(name: str) -> logging.Logger:
    log_level = logging.INFO

    if name is None or not isinstance(name, str) or len(name) == 0:
        raise ValueError("Name must be a non-empty string.")

    logger = logging.getLogger(name)
    stream_handler = logging.StreamHandler()
    stream_handler.setFormatter(logging.Formatter(LOG_FORMAT))

    # Only add Datadog filter when Datadog is configured
    if _is_datadog_configured:
        stream_handler.addFilter(DatadogLogFilter())

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
