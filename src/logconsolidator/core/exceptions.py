class PipelineError(Exception):
    """Base exception for pipeline failures."""


class ConfigError(PipelineError):
    """Raised when configuration is invalid."""
