import logging


def configure_logging(level: str = "INFO") -> logging.Logger:
    """Configure root logging once and return the project logger."""
    logging.basicConfig(
        level=level,
        format="%(asctime)s %(levelname)s %(threadName)s %(message)s",
    )
    return logging.getLogger("logconsolidator")
