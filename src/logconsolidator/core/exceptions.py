class PipelineError(Exception):
    """Base exception type for pipeline-related failures."""


class ConfigError(PipelineError):
    """Raised when source configuration is missing or invalid."""
