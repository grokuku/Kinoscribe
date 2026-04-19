"""
Structured logging setup using structlog.
Provides a consistent, JSON-friendly logger across the application.
"""

import logging
import structlog


def setup_logging(debug: bool = False) -> None:
    """Configure structlog + stdlib logging once at startup."""
    log_level = logging.DEBUG if debug else logging.INFO

    structlog.configure(
        processors=[
            structlog.contextvars.merge_contextvars,
            structlog.stdlib.add_log_level,
            structlog.stdlib.add_logger_name,
            structlog.processors.TimeStamper(fmt="iso"),
            structlog.processors.StackInfoRenderer(),
            structlog.processors.format_exc_info,
            structlog.dev.ConsoleRenderer() if debug else structlog.processors.JSONRenderer(),
        ],
        wrapper_class=structlog.stdlib.BoundLogger,
        context_class=dict,
        logger_factory=structlog.stdlib.LoggerFactory(),
        cache_logger_on_first_use=True,
    )

    # Also configure stdlib root logger so that libs using `logging` are captured
    root = logging.getLogger()
    root.setLevel(log_level)
    handler = logging.StreamHandler()
    handler.setFormatter(structlog.stdlib.ProcessorFormatter(
        processor=structlog.dev.ConsoleRenderer() if debug else structlog.processors.JSONRenderer(),
    ))
    root.handlers.clear()
    root.addHandler(handler)


def get_logger(name: str = __name__) -> structlog.stdlib.BoundLogger:
    """Return a bound structlog logger."""
    return structlog.get_logger(name)