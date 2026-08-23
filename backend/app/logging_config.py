import logging
import sys

# Uvicorn installs its own logging configuration when it boots, and it does
# so around the time the app module is imported. Relying only on the root
# logger is therefore fragile: depending on ordering, our handler can be
# replaced and application logs vanish. Attaching a handler directly to the
# loggers we own, with propagate off, makes their output independent of
# whatever uvicorn decides to do with the root logger.
LOG_FORMAT = "%(asctime)s %(levelname)-7s %(name)s | %(message)s"
DATE_FORMAT = "%H:%M:%S"

# Loggers this application writes to.
APP_LOGGERS = ("indexing", "indexing.queue", "app")


def _make_handler() -> logging.Handler:
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(logging.Formatter(LOG_FORMAT, datefmt=DATE_FORMAT))
    return handler


def configure_logging(level: int = logging.INFO) -> None:
    root = logging.getLogger()
    if not any(getattr(h, "_pr_reviewer", False) for h in root.handlers):
        handler = _make_handler()
        handler._pr_reviewer = True  # type: ignore[attr-defined]
        root.addHandler(handler)
    root.setLevel(level)

    for name in APP_LOGGERS:
        logger = logging.getLogger(name)
        # Clear on re-run so `--reload` does not stack duplicate handlers
        # and print every line twice.
        for existing in [h for h in logger.handlers if getattr(h, "_pr_reviewer", False)]:
            logger.removeHandler(existing)
        handler = _make_handler()
        handler._pr_reviewer = True  # type: ignore[attr-defined]
        logger.addHandler(handler)
        logger.setLevel(level)
        # Own handler already prints it; propagating would duplicate the line.
        logger.propagate = False

    # Noisy at INFO, and they drown out anything useful.
    logging.getLogger("httpx").setLevel(logging.WARNING)
    logging.getLogger("httpcore").setLevel(logging.WARNING)
