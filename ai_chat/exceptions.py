class AgentConfigurationError(ValueError):
    """Raised when an agent is missing required configuration."""


class AgentResponseError(RuntimeError):
    """Raised when a provider response cannot be converted into text."""
